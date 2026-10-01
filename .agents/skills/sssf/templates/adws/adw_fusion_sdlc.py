#!/usr/bin/env -S uv run
# /// script
# dependencies = ["pydantic", "python-dotenv", "pyyaml", "rich"]
# ///
"""Fusion consensus in place of the single planner, then the full verified SDLC.

Phases: engineer(request) -> opinions -> critique -> synthesis -> votes -> consensus
        -> [the entire adw_simple_sdlc chain, implementing the agreed plan]

The planner is the highest-leverage phase in the factory and the one a single
model is least reliable at: a bad plan compounds through every phase after it.
This replaces that one model with a panel that must reach unanimous agreement
before a single line is written, then hands the agreed plan to the ordinary
SDLC — same builder, same independent tests, same mutation proof, same review.

Consensus is model agreement, NOT user approval. Without unanimity nothing is
implemented and nothing is committed: dissent is a reason to stop, not a
formality to log on the way past.
"""

import argparse
import json
import sys

import adw_fusion_plan
import adw_simple_sdlc
from adw_modules import agents, session, utils
from adw_modules.fusion_recovery import Checkpoint, RecoveryOptions


def main(prompt: str, models: list[str] | None,
         config: str = "adws/adw_sssf_config/sssf.config.yaml",
         adw_id: str | None = None, auto_approve: bool = False,
         openers: list[str] | None = None, recovery: RecoveryOptions | None = None,
         synthesizer_model: str | None = None, panel_name: str | None = None,
         allow_single_family: bool = False) -> int:
    if recovery and recovery.resume and not adw_id:
        raise ValueError("--resume requires the original --adw-id")
    cfg = agents.load_config(config)
    run = session.ensure(cfg, adw_id)
    approved, plan_path = adw_fusion_plan.debate(
        run, cfg, prompt, models, openers, recovery, synthesizer_model, panel_name, allow_single_family)

    if not approved:
        run.console.note(f"No consensus. Nothing was implemented. Inspect the dissent "
                         f"beside {plan_path}.")
        return run.finish(accepted=False,
                          reason="Fusion did not reach unanimous agreement; nothing was built")

    # The plan the panel agreed on is now an ordinary approved plan, so the
    # verified SDLC runs unchanged — it never learns that a panel wrote it.
    run.console.note(f"Unanimous consensus. Implementing {plan_path}.")
    # Fusion replay is read-only. Never accidentally re-run SDLC commits on --resume.
    with Checkpoint(run, cfg, recovery or RecoveryOptions()) as checkpoint:
        checkpoint.state = json.loads(checkpoint.path.read_text())
        if checkpoint.state.get("implementation_started"):
            raise ValueError("SDLC implementation already started; automatic replay is unsafe")
        checkpoint.state["implementation_started"] = True
        checkpoint.save()
    return adw_simple_sdlc.main(
        prompt, config, run.adw_id,
        adw_simple_sdlc.SdlcOptions(approved_plan=str(plan_path), auto_approve=auto_approve))


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
    parser.add_argument("--resume", action="store_true", help="resume only the read-only Fusion planning stage")
    parser.add_argument("--fallback-models", nargs="+", default=[], help="unused same-family spare models")
    parser.add_argument("--yes", action="store_true",
                        help="skip the human release gate before the verified work is committed")
    parser.add_argument("--allow-single-family", action="store_true",
                        help="monofuse mode: permit --models from one family (e.g. Codex-only), "
                             "for when another provider is down. A deliberate opt-in, never the "
                             "default — this run also builds and commits, so treat it the same "
                             "as any other explicit --models override, not as a routine choice.")
    args = parser.parse_args()
    sys.exit(main(utils.resolve_prompt(args.prompt), args.models, args.config,
                  args.adw_id, args.yes, args.opening_models,
                  RecoveryOptions(args.resume, args.fallback_models),
                  args.synthesizer_model, args.panel, args.allow_single_family))
