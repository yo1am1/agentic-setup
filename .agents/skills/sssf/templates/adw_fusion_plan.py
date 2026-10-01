#!/usr/bin/env -S uv run
# /// script
# dependencies = ["pydantic", "python-dotenv", "pyyaml", "rich"]
# ///
"""Optional Fusion-style planning: independent opinions → debate → synthesis → votes.

Phases: engineer(request) -> opinions -> critique -> synthesis -> votes -> code(consensus)

Native SSSF adaptation of disler/fusion-harness, not its Pi extension runtime.
Uses 3–12 distinct models from at least two families, two immutable opinion rounds, and at most
two synthesized plans. Unanimous approval means model agreement, NOT user approval.
Never builds or commits. Every draft and dissent remains in context_handoff/.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from adw_modules import agents, fusion, gates, session, utils
from adw_modules.fusion_recovery import Checkpoint, RecoveryOptions
from adw_modules.data_types import (AgentCall, FusionOpinionOutput, FusionPlanOutput,
                                    FusionVoteOutput, GenericOutput, PhaseParams)


def debate(run, cfg, prompt: str, models: list[str] | None,
           openers: list[str] | None = None, recovery: RecoveryOptions | None = None,
           synthesizer_model: str | None = None,
           panel_name: str | None = None) -> tuple[bool, Path]:
    """Run the whole debate and return (unanimous, plan_path).

    Separate from main() so a workflow that implements the consensus runs the
    identical protocol in the same session, rather than re-deriving it. The
    caller owns what happens next; this owns only how models argue.
    """
    # One place resolves the roster's configured panel, so every workflow that
    # convenes one — and the checkpoint that records what it convened — sees the
    # same models the run will actually use.
    models, openers, synthesizer_model = fusion.with_defaults(
        cfg, models, openers, synthesizer_model, panel_name)
    allow_single_family = fusion.allow_single_family(cfg, models, panel_name)
    thinking = fusion.panel_thinking(cfg, models, panel_name)
    allow_external_synthesizer = fusion.allow_external_synthesizer(cfg, models, panel_name)
    with Checkpoint(run, cfg, recovery or RecoveryOptions()) as checkpoint:
        prepared = False
        try:
            tag = checkpoint.prepare(prompt, models, openers, synthesizer_model)
            participants, opening, synthesizer, tag = fusion.configure(
                cfg, models, openers, tag, synthesizer_model, allow_single_family, thinking,
                allow_external_synthesizer)
            checkpoint.bind([*participants, *opening, synthesizer])
            prepared = True
            result = _debate(run, cfg, prompt, (participants, opening, synthesizer, tag), checkpoint)
            checkpoint.state["status"] = "complete"
            checkpoint.save()
            return result
        except BaseException:
            # Validation must never overwrite a checkpoint belonging to different inputs.
            if prepared:
                checkpoint.state["status"] = "blocked"
                checkpoint.save()
            run.finish(accepted=False, reason="Fusion stopped; accepted answers are checkpointed for --resume")
            raise


def _debate(run, cfg, prompt, panel, checkpoint):
    participants, opening, synthesizer, tag = panel
    models = [agents.resolve(cfg, name).model for name in participants]
    directory = run.context_handoff_dir / f"fusion_{tag}"
    directory.mkdir(parents=True, exist_ok=True)

    with run.phase(PhaseParams(name="request", kind="engineer", owner=run.engineer,
                               description="Capture the planning request and model roster")) as ph:
        ph.log(input=prompt, models=models, requires_human_approval=True)

    history = []
    previous = None
    active = list(participants)
    # Opening voices speak once. They are heard and argued with, never counted:
    # a model that cannot survive a full round has no business ratifying a plan.
    speaking = [*participants, *opening]
    # A round is a barrier, not a queue: round 1 is independent by definition
    # and round 2 critiques the *frozen* round-1 set, so no seat has ever been
    # an input to another seat in the same round. They ran sequentially only
    # because the tracer, the phase counter and the checkpoint were
    # single-threaded; now that they are not, a round costs its slowest seat
    # instead of the sum of all of them. fusion.in_parallel falls back to
    # sequential on its own if any participant is not read-only.
    for round_number in (1, 2):
        speakers = [p for p in speaking if p in active or p in opening]

        def propose(participant, round_number=round_number, previous=previous):
            return checkpoint.call(
                PhaseParams(name=f"opinion_{round_number}_{participant}", kind="agent",
                            owner=participant, description="Independent proposal" if round_number == 1
                            else "Critique the same frozen previous-round proposals"),
                AgentCall(output_type=FusionOpinionOutput, prompt=prompt,
                          previous=previous, record_questions=True))

        opinions = {name: opinion.model_dump()
                    for name, opinion in fusion.in_parallel(cfg, speakers, propose).items()}
        history.append(opinions)
        speaking = list(active)          # openers propose once, then fall silent
        artifact = fusion.save(directory / f"opinions_{round_number}.json", opinions)
        previous = GenericOutput(status="success", artifacts=[artifact],
                                  summary=json.dumps(opinions),
                                  notes_for_next_agent="Critique these proposals; retain disagreements and evidence.")

    previous = GenericOutput(status="success", summary=json.dumps(history),
                              notes_for_next_agent="Synthesize a minimal implementable plan from both rounds.")
    approved = False
    for attempt in (1, 2):
        draft = checkpoint.call(
            PhaseParams(name=f"synthesize_{attempt}", kind="agent", owner=synthesizer,
                        description="Synthesize the proposals without implementing anything"),
            AgentCall(output_type=FusionPlanOutput, prompt=prompt, previous=previous,
                      record_questions=True))
        plan_path = directory / f"plan_{attempt}.md"
        plan_path.write_text(draft.plan)
        digest = hashlib.sha256(draft.plan.encode()).hexdigest()
        shared_plan = GenericOutput(status="success", summary=draft.plan,
                                     artifacts=[str(plan_path)], notes_for_next_agent=f"plan_sha256={digest}")

        def ballot(participant, attempt=attempt, shared_plan=shared_plan, digest=digest):
            # A vote is a comparison, not an inquiry: read the exact plan, check
            # the hash, approve or dissent. It re-uses the debating seat — same
            # model, same session, same context — but at the effort the step
            # actually needs rather than the one its opinions needed.
            #
            # Every seat votes on one hash-pinned plan and reads nothing from
            # another voter, so the ballot is a fan-out like the rounds. Each
            # thread retunes only its own seat's config; `resolve` hands back a
            # different object per name.
            seat = agents.resolve(cfg, participant)
            seat.prompt_engineering.user = f"{fusion.PROMPTS}/vote.md"
            seat.thinking = cfg.fusion.thinking.vote
            return checkpoint.call(
                    PhaseParams(name=f"vote_{attempt}_{participant}", kind="agent",
                                owner=participant, retries=1,
                                description="Review the exact shared plan; dissent is allowed"),
                    AgentCall(output_type=FusionVoteOutput, prompt=prompt, previous=shared_plan,
                              record_questions=True,
                              gates=[gates.verdict_consistent, fusion.reviewed_exact_plan(digest)]))

        votes = {name: vote.model_dump()
                 for name, vote in fusion.in_parallel(cfg, list(active), ballot).items()}
        # All declared seats must vote. Unavailable seats are resumed/replaced, never dropped.
        approved = bool(votes) and all(vote["approved"] for vote in votes.values())
        report = dict(consensus=approved, requires_human_approval=True,
                      models={name: agents.resolve(cfg, name).model for name in participants},
                      substitutions=checkpoint.state["substitutions"],
                      step_models={key: value["model"] for key, value in checkpoint.state["steps"].items()},
                      panel_declared=len(participants), panel_voting=len(votes),
                      opening_voices=len(opening),
                      plan_path=str(plan_path), plan_sha256=digest, votes=votes)
        # A later replacement must not rewrite the rejected report used to create plan 2.
        report = checkpoint.state.setdefault("reports", {}).setdefault(str(attempt), json.loads(json.dumps(report)))
        checkpoint.save()
        with run.phase(PhaseParams(name=f"consensus_{attempt}", kind="code", owner="fusion",
                                   description="Record unanimous agreement or unresolved dissent")) as ph:
            ph.log(consensus=approved, report=fusion.save(directory / f"consensus_{attempt}.json", report),
                   plan=str(plan_path), requires_human_approval=True)
        if approved:
            break
        previous = GenericOutput(status="success", summary=json.dumps(report),
                                  notes_for_next_agent="Revise the plan to address dissent, without hiding tradeoffs.")

    return approved, plan_path


def main(prompt: str, models: list[str] | None,
         config: str = "adws/adw_sssf_config/sssf.config.yaml",
         adw_id: str | None = None, openers: list[str] | None = None,
         recovery: RecoveryOptions | None = None, synthesizer_model: str | None = None,
         panel_name: str | None = None) -> int:
    if recovery and recovery.resume and not adw_id:
        raise ValueError("--resume requires the original --adw-id")
    cfg = agents.load_config(config)
    run = session.ensure(cfg, adw_id)
    approved, plan_path = debate(
        run, cfg, prompt, models, openers, recovery, synthesizer_model, panel_name)
    run.console.note(f"Review plan: {plan_path}. Human approval is required before implementation.")
    return run.finish(accepted=approved, reason="Fusion did not reach unanimous agreement; inspect dissent")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", help="inline request or prompt file")
    parser.add_argument("--models", nargs="+", default=None,
                        help="3–12 distinct models, at least two families; overrides --panel")
    parser.add_argument("--panel", default=None,
                        help="named panel under fusion.panels; omitted: fusion.use")
    parser.add_argument("--synthesizer-model", default=None,
                        help="panel member that turns the debate into the plan (default: the "
                             "roster's fusion.synthesizer, else the first model)")
    parser.add_argument("--opening-models", nargs="*", default=None,
                        help="opening-round-only voices: they propose and are critiqued, never vote")
    parser.add_argument("--config", default="adws/adw_sssf_config/sssf.config.yaml")
    parser.add_argument("--adw-id", default=None)
    parser.add_argument("--resume", action="store_true", help="reuse this session's accepted Fusion answers")
    parser.add_argument("--fallback-models", nargs="+", default=[],
                        help="explicit spare models; unused same-family reserves replace failed seats")
    args = parser.parse_args()
    sys.exit(main(utils.resolve_prompt(args.prompt), args.models, args.config, args.adw_id,
                  args.opening_models, RecoveryOptions(args.resume, args.fallback_models),
                  args.synthesizer_model, args.panel))
