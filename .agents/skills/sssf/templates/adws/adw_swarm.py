#!/usr/bin/env -S uv run
# /// script
# dependencies = ["pydantic", "python-dotenv", "pyyaml", "rich"]
# ///
"""ADW Swarm — N peer agents, one shared board, rounds until done or out of budget.

Usage:
    uv run adws/adw_swarm.py "<goal or path/to/goal.md>" --dod "<definition of done>"
        [--models m1 m2 m3] [--rounds 6] [--budget 5.0]
        [--config adws/adw_sssf_config/sssf.config.yaml] [--adw-id a1b2c3d4]

Phases: engineer(request) -> r1_swarm_1 .. r1_swarm_N -> r2_... -> reviewer(verify)

Peers, not a pipeline (IndyDevDan "Simple Swarm" pattern): no planner assigns
work. Each round every live seat reads the board (goal, definition of done,
posts, claims, budget left), takes one step, and returns posts/claims/done.
Claims are first-come file locks and become that seat's `writes` allowlist from
the next round on, so `permissions.enforce` rolls back any write outside it.
A round of writing seats runs sequentially (`fusion.in_parallel` refuses to fan
out writers — interleaved tree snapshots would blame and revert a peer's work);
a round in which nobody holds a grant yet fans out.

Stops when every live seat says done in the same round (then the roster's
reviewer must approve against the definition of done), or on budget, round
cap, or two rounds in a row with no progress. Never commits.
"""

import argparse
import json
import sys

from adw_modules import agents, fusion, session, utils
from adw_modules.data_types import (AgentCall, AgentConfig, EnvelopeBase, PhaseParams,
                                    PromptEngineering, ReviewOutput)
from pydantic import Field

PROMPTS = "adws/adw_data/prompt_engineering/swarm"
TOOLS = ["read", "grep", "find", "ls", "bash", "edit", "write"]
STALL_LIMIT = 2
DROP_AFTER = 2       # consecutive failed turns (e.g. a quota-dead provider) before a seat is dropped
BOARD_TAIL = 40


class SwarmTurnOutput(EnvelopeBase):
    posts: list[str] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    done: bool = False
    done_reason: str = ""


def grant(owners: dict[str, str], seat: str, paths: list[str]) -> list[str]:
    """First come, first served: a path goes to the first seat that claims it."""
    for path in paths:
        path = path.strip().lstrip("./")
        if path and path not in owners:
            owners[path] = seat
    return sorted(p for p, s in owners.items() if s == seat)


def render(goal: str, dod: str, seat: str, board: dict, budget_left: float) -> str:
    claims = "\n".join(f"- {p}: {s}" for p, s in sorted(board["claims"].items())) or "(none)"
    posts = "\n".join(f"[r{p['round']}] {p['seat']}: {p['text']}"
                      for p in board["posts"][-BOARD_TAIL:]) or "(empty)"
    mine = sorted(p for p, s in board["claims"].items() if s == seat) or ["(none — claim first)"]
    return (f"# Goal\n{goal}\n\n# Definition of done\n{dod}\n\n# You\n{seat}\n"
            f"Paths granted to you now: {', '.join(mine)}\n\n"
            f"# Budget left\n${budget_left:.2f}\n\n# Claims\n{claims}\n\n# Board\n{posts}\n")


def main(goal: str, dod: str, models: list[str] | None = None, rounds: int = 6,
         budget: float = 5.0, config: str = "adws/adw_sssf_config/sssf.config.yaml",
         adw_id: str | None = None) -> int:
    if not dod.strip():
        raise SystemExit("a swarm needs --dod: without a definition of done nobody can stop")
    cfg = agents.load_config(config)
    models = models or fusion.with_defaults(cfg, None, None, None)[0]
    if len(models) < 2:
        raise SystemExit("a swarm needs at least 2 seats")
    tag = utils.new_id(6)
    seats = [f"swarm_{i}_{tag}" for i in range(1, len(models) + 1)]
    for seat, model in zip(seats, models, strict=True):
        cfg.agents.append(AgentConfig(
            name=seat, model=model, thinking=cfg.fusion.thinking.opinion,
            purpose="Swarm peer: claim, build, critique, declare done",
            prompt_engineering=PromptEngineering(system=f"{PROMPTS}/system.md",
                                                 user=f"{PROMPTS}/user.md"),
            tools=TOOLS, writes=[]))
    agents.validate(cfg, [*seats, "reviewer"])
    run = session.ensure(cfg, adw_id)
    board_path = run.context_handoff_dir / "board.json"
    board = {"goal": goal, "dod": dod, "claims": {}, "posts": [], "done": {}}

    with run.phase(PhaseParams(name="request", kind="engineer", owner=run.engineer,
                               description="Capture the swarm goal and its definition of done")) as ph:
        ph.log(input=goal, dod=dod, seats=dict(zip(seats, models, strict=True)),
               rounds=rounds, budget=budget)

    live, stalls, finished, reason = list(seats), 0, False, "round cap reached"
    failures = dict.fromkeys(seats, 0)
    for n in range(1, rounds + 1):
        if run.cost >= budget:
            reason = f"budget spent (${run.cost:.2f} of ${budget:.2f})"
            break
        # Grants are fixed for the whole round, so seats in it never race for a path.
        for seat in live:
            agents.resolve(cfg, seat).writes = sorted(
                p for p, s in board["claims"].items() if s == seat)
        prompt = {seat: render(goal, dod, seat, board, budget - run.cost) for seat in live}

        def turn(seat, n=n, prompt=prompt):
            try:
                with run.phase(PhaseParams(
                        name=f"r{n}_{seat}", kind="agent", owner=seat, recoverable=True,
                        description=f"Swarm round {n}: read the board, take one step")) as ph:
                    return ph.call(AgentCall(output_type=SwarmTurnOutput, prompt=prompt[seat],
                                             record_questions=True))
            except Exception as error:  # a failed peer is reported, not fatal to the swarm
                return str(error)[:300]

        results = fusion.in_parallel(cfg, live, turn)
        progress = False
        for seat in live:
            out = results[seat]
            if isinstance(out, str):
                board["posts"].append({"round": n, "seat": seat, "text": f"(turn failed: {out})"})
                board["done"][seat] = False
                failures[seat] += 1
                continue
            failures[seat] = 0
            for text in out.posts:
                board["posts"].append({"round": n, "seat": seat, "text": text})
            before = len(board["claims"])
            grant(board["claims"], seat, out.claims)
            progress |= bool(out.posts or out.changed_files or len(board["claims"]) > before)
            board["done"][seat] = out.done
            if out.done:
                board["posts"].append({"round": n, "seat": seat, "text": f"DONE: {out.done_reason}"})
        for seat in [s for s in live if failures[s] >= DROP_AFTER]:
            live.remove(seat)
            board["done"].pop(seat, None)
            board["posts"].append({"round": n, "seat": seat, "text": f"(dropped after {DROP_AFTER} failed turns)"})
        fusion.save(board_path, board)
        if not live:
            reason = "every seat failed"
            break
        if all(board["done"].get(seat) for seat in live):
            finished, reason = True, f"all seats done in round {n}"
            break
        stalls = 0 if progress else stalls + 1
        if stalls >= STALL_LIMIT:
            reason = f"no progress for {STALL_LIMIT} rounds"
            break

    approved = False
    if finished:
        with run.phase(PhaseParams(name="verify", kind="agent", owner="reviewer",
                                   description="Check the swarm's work against the definition of done")) as ph:
            review = ph.call(AgentCall(output_type=ReviewOutput, prompt=(
                f"{goal}\n\n## Definition of done\n{dod}\n\nThe swarm board is at "
                f"{board_path}; changed paths: {json.dumps(sorted(board['claims']))}")))
            approved = review.approved
            reason = reason if approved else "reviewer rejected: " + "; ".join(review.blocking)
    return run.finish(accepted=approved, reason=reason)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("prompt", help="inline goal or a path to a goal file")
    parser.add_argument("--dod", required=True, help="definition of done, with how to validate it")
    parser.add_argument("--models", nargs="+", default=None, help="one seat per model (default: roster fusion panel)")
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--budget", type=float, default=5.0, help="USD cap across all seats")
    parser.add_argument("--config", default="adws/adw_sssf_config/sssf.config.yaml")
    parser.add_argument("--adw-id", default=None, help="join or pin an existing session")
    args = parser.parse_args()
    sys.exit(main(utils.resolve_prompt(args.prompt), args.dod, args.models, args.rounds,
                  args.budget, args.config, args.adw_id))
