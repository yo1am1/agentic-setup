#!/usr/bin/env -S uv run
# /// script
# dependencies = ["pydantic", "python-dotenv", "pyyaml", "rich"]
# ///
"""ADW Simple SDLC — plan, prove, build, verify, and document.

Usage:
    uv run adws/adw_simple_sdlc.py "<prompt or path/to/prompt.md>" [--config adws/adw_sssf_config/sssf.config.yaml] [--adw-id a1b2c3d4]

Phases: engineer(request) -> planner -> git(commit_plan)
        -> test_writer -> code(test_baseline)
        -> builder -> code(static) -> code(test) -> test_reviewer
        -> code(mutations) -> reviewer [-> repair and reverify ... bounded]
        -> git(commit_build) -> code(changes) -> documenter -> git(commit_docs)

Tests are written from the plan before implementation. The baseline may be green
when adding coverage to existing behavior. After implementation, reviewed faults
must trigger assertion failures in disposable copies. Tests stay uncommitted and
are protected by recoverable content snapshots until the verified code commit.

Testing is CODE, not an agent. `bun test` is a command, not a judgement call:
an agent rediscovering it every run costs a million tokens to learn what a
subprocess already knows. Failures travel back to the builder as an envelope,
so the repair loop is unchanged — only the runner became free and repeatable.

Static checks ask whether the code is well-formed, the suite asks whether it
runs, and the reviewer asks whether it is what was requested. No verdict covers
for another, and a revision re-enters both deterministic checks.

The code commit lands after verification, not straight after the build: fixes
and revisions are part of the same work product, and red code has no business
on the branch. A run that fails verification therefore leaves the plan
committed and the working tree dirty — the spec is a real artifact either way,
and the unfinished code stays where the engineer can see it.

The documenter measures against the commit this run STARTED from, not against
`main`, because by then the run has moved `main` itself. That baseline is
pinned before the first commit phase and printed in the request phase.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from adw_modules import agents, changes, gates, git_helper, mutations, quality, session, utils
from adw_modules.data_types import (AgentCall, BuildOutput, ChangeCapture,
                                    DocumentOutput, PhaseParams, PlanOutput,
                                    ReviewOutput, TestReviewOutput)

REQUIRED_AGENTS = ["planner", "test_writer", "test_reviewer", "builder",
                   "reviewer", "documenter"]
MAX_FIX_LOOPS = 3
MAX_REVISION_LOOPS = 2

DOCUMENT_NOTES = ("Read diff_path in full before writing. Document only what the "
                  "diff shows, then copy the write-up into app_docs/ as your task "
                  "describes.")


@dataclass
class SdlcOptions:
    approved_plan: str | None = None
    auto_approve: bool = False


def main(prompt: str, config: str = "adws/adw_sssf_config/sssf.config.yaml",
         adw_id: str | None = None, options: SdlcOptions | None = None) -> int:
    options = options or SdlcOptions()
    cfg = agents.load_config(config)
    agents.validate(cfg, [name for name in REQUIRED_AGENTS
                          if name != "planner" or not options.approved_plan])
    run = session.ensure(cfg, adw_id)
    baseline = git_helper.rev("HEAD")     # pinned before this run commits anything

    def commit(ph, envelope) -> None:
        """Commit what the preceding phase produced, in that agent's own words."""
        message = envelope.commit_message or f"sssf({run.adw_id}): {envelope.summary}"
        ph.log(sha=git_helper.commit_all(message), message=message)

    def record(ph, result) -> None:
        """Log a deterministic block's verdict — the same shape every ADW uses."""
        passed = sum(1 for check in result.checks if check.passed)
        ph.log(passed=result.passed, checks=f"{passed}/{len(result.checks)}",
               artifacts=", ".join(result.artifacts))

    def repair(cycle, build):
        """Every edit invalidates both verdicts; always restart at static checks."""
        result = None
        for attempt in range(1, MAX_FIX_LOOPS + 1):
            for kind, checker in (("static_quality", quality.run_static_quality),
                                  ("test", quality.run_tests)):
                with run.phase(PhaseParams(name=f"{kind}_{cycle}_{attempt}", kind="code",
                                           owner="quality", description=f"Run deterministic {kind}")) as ph:
                    result = checker(run)
                    record(ph, result)
                if not result.passed:
                    break
            if result.passed or attempt == MAX_FIX_LOOPS:
                break
            with run.phase(PhaseParams(name=f"fix_{kind}_{cycle}_{attempt}", kind="agent",
                                       owner="builder", retries=1,
                                       description=f"Repair reported {kind} failures")) as ph:
                build = ph.call(AgentCall(output_type=BuildOutput, prompt=prompt,
                                          previous=quality.as_envelope(result, kind),
                                          gates=[gates.diff_matches_claims],
                                          allow_questions=True))
        return result, build

    with run.phase(PhaseParams(name="request", kind="engineer", owner=run.engineer,
                               description="Capture the incoming ask")) as ph:
        ph.log(input=prompt, baseline=git_helper.short_sha(baseline))

    if options.approved_plan:
        with run.phase(PhaseParams(name="record_fusion_plan", kind="code", owner="fusion",
                                   description="Copy the human-approved consensus into the tracked specs")) as ph:
            source = Path(options.approved_plan)
            if not source.is_file():
                raise RuntimeError(f"approved Fusion plan not found: {source}")
            target = Path("specs") / f"{run.adw_id}_fusion-plan.md"
            target.parent.mkdir(exist_ok=True)
            target.write_text(source.read_text())
            plan = PlanOutput(status="success", summary="Human-approved Fusion plan",
                              artifacts=[str(target)], commit_message="Record approved Fusion plan")
            ph.log(source=str(source), plan=str(target))
    else:
        with run.phase(PhaseParams(name="plan", kind="agent", owner="planner",
                                   description="Turn the request into an implementable plan")) as ph:
            plan = ph.call(AgentCall(output_type=PlanOutput, prompt=prompt,
                                     gates=[gates.artifacts_exist, gates.files_non_empty],
                                     allow_questions=True))

    with run.phase(PhaseParams(name="commit_plan", kind="code", owner="git",
                               description="Put the spec on record before any code exists to blur it")) as ph:
        commit(ph, plan)

    with run.phase(PhaseParams(name="write_tests", kind="agent", owner="test_writer", retries=1,
                               description="Write behavioral tests from the plan before implementation")) as ph:
        ph.call(AgentCall(output_type=BuildOutput, prompt=prompt, previous=plan,
                          gates=[gates.diff_matches_claims], allow_questions=True))

    with run.phase(PhaseParams(name="test_baseline", kind="code", owner="quality",
                               description="Record which behavior already works before building")) as ph:
        record(ph, quality.run_tests(run))

    with run.phase(PhaseParams(name="build", kind="agent", owner="builder",
                               description="Implement the plan exactly")) as ph:
        build = ph.call(AgentCall(output_type=BuildOutput, prompt=prompt, previous=plan,
                                  gates=[gates.diff_matches_claims], allow_questions=True))

    verified = False
    for i in range(1, MAX_REVISION_LOOPS + 1):
        checks, build = repair(i, build)
        if not checks.passed:
            break

        with run.phase(PhaseParams(name=f"challenge_tests_{i}", kind="agent", owner="test_reviewer", retries=1,
                                   description="Challenge assertions and specify realistic production faults")) as ph:
            test_review = ph.call(AgentCall(output_type=TestReviewOutput, prompt=prompt,
                                            previous=quality.as_envelope(checks, "tests"),
                                            gates=[gates.artifacts_exist, gates.verdict_consistent,
                                                   mutations.validate_cases], allow_questions=True))
        if test_review.approved:
            with run.phase(PhaseParams(name=f"mutations_{i}", kind="code", owner="quality",
                                       description="Break production logic in disposable copies and demand failing assertions")) as ph:
                proof = mutations.run_mutations(run, test_review.mutations)
                record(ph, proof)
            feedback = quality.as_envelope(proof, "mutation strength")
        else:
            feedback = test_review
        if not test_review.approved or not proof.passed:
            if i == MAX_REVISION_LOOPS:
                break
            with run.phase(PhaseParams(name=f"strengthen_tests_{i}", kind="agent", owner="test_writer", retries=1,
                                       description="Add assertions that catch the reported surviving faults")) as ph:
                ph.call(AgentCall(output_type=BuildOutput, prompt=prompt, previous=feedback,
                                  gates=[gates.diff_matches_claims], allow_questions=True))
            continue

        with run.phase(PhaseParams(name=f"review_{i}", kind="agent", owner="reviewer",
                                   description="Confirm the build matches the plan")) as ph:
            review = ph.call(AgentCall(output_type=ReviewOutput, prompt=prompt, previous=build,
                                       gates=[gates.artifacts_exist, gates.verdict_consistent],
                                       allow_questions=True))

        verified = review.approved
        if verified or i == MAX_REVISION_LOOPS:
            break

        with run.phase(PhaseParams(name=f"revise_{i}", kind="agent", owner="builder", retries=1,
                                   description="Close the reviewer's blocking findings")) as ph:
            build = ph.call(AgentCall(output_type=BuildOutput, prompt=prompt, previous=review,
                                      gates=[gates.diff_matches_claims], allow_questions=True))

    # Red tests or a rejected review stop the chain here: the code stays
    # uncommitted and nothing is documented, because there is nothing worth
    # describing yet. The plan commit stands — it is a record of what was asked.
    if verified:
        with run.phase(PhaseParams(name="approve_release", kind="engineer", owner=run.engineer,
                                   description="Let the engineer inspect verification before commits land")) as ph:
            if options.auto_approve:
                release_approved = True
            elif not sys.stdin.isatty():
                raise RuntimeError("release approval needs an interactive terminal; use --yes only in CI")
            else:
                release_approved = input("Verification passed. Commit code and documentation? [y/N] ").strip().lower() in {"y", "yes"}
            ph.log(approved=release_approved)
        verified = verified and release_approved

    if verified:
        with run.phase(PhaseParams(name="commit_build", kind="code", owner="git",
                                   description="Land the code only now: green suite, approved review")) as ph:
            commit(ph, build)

        with run.phase(PhaseParams(name="changes", kind="code", owner="git",
                                   description="Diff the whole run against its pinned baseline, for the documenter")) as ph:
            changeset = changes.capture(run, ChangeCapture(base=baseline))
            ph.log(base=f"{changeset.base.label} @ {changeset.base.commit[:7]}",
                   reason=changeset.base.reason,
                   files=len(changeset.files) + len(changeset.untracked),
                   lines=f"+{changeset.insertions} -{changeset.deletions}",
                   diff=changeset.diff_path)
            if changeset.empty:
                raise RuntimeError(
                    f"nothing changed since {changeset.base.label} "
                    f"({changeset.base.reason}) — there is nothing to document.")

        with run.phase(PhaseParams(name="document", kind="agent", owner="documenter", retries=1,
                                   description="Write up the completed change")) as ph:
            document = ph.call(AgentCall(output_type=DocumentOutput, prompt=prompt,
                                         previous=changes.as_envelope(changeset, DOCUMENT_NOTES),
                                         gates=[gates.artifacts_exist, gates.files_non_empty],
                                         allow_questions=True))

        with run.phase(PhaseParams(name="commit_docs", kind="code", owner="git",
                                   description="Ship the write-up in its own commit, beside the code it describes")) as ph:
            commit(ph, document)

    return run.finish(accepted=verified,
                      reason="static quality, tests, mutation probes, or review never came back clean")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", help="inline text or a path to a prompt file")
    parser.add_argument("--config", default="adws/adw_sssf_config/sssf.config.yaml")
    parser.add_argument("--adw-id", default=None, help="join or pin an existing session")
    parser.add_argument("--approved-plan", default=None, help="human-approved Fusion plan to implement")
    parser.add_argument("--yes", action="store_true", help="accept the final release gate (CI only)")
    args = parser.parse_args()
    sys.exit(main(utils.resolve_prompt(args.prompt), args.config, args.adw_id,
                  SdlcOptions(args.approved_plan, args.yes)))
