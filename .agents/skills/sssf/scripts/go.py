#!/usr/bin/env -S uv run
# /// script
# dependencies = []
# ///
"""Run one supported SSSF mode through the shared engine."""

from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
ENGINE = SKILL / "templates" / "adws"
MODES = {
    "scout": "adw_scout.py",
    "plan": "adw_plan.py",
    "fusion": "adw_fusion_plan.py",
    "sdlc": "adw_plan_build_test.py",
    "ssdlc": "adw_simple_sdlc.py",
}


@dataclass
class Workflow:
    script: str
    prompt: str
    config: str
    adw_id: str | None = None
    models: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)


def choose(label: str, values: list[str]) -> str:
    print(label)
    for index, value in enumerate(values, 1):
        print(f"  {index}. {value}")
    answer = input("> ").strip()
    if answer.isdigit() and 1 <= int(answer) <= len(values):
        return values[int(answer) - 1]
    if answer in values:
        return answer
    raise SystemExit(f"choose one of: {', '.join(values)}")


def run(request: Workflow) -> int:
    argv = ["uv", "run", str(ENGINE / request.script), request.prompt,
            "--config", request.config]
    if request.adw_id:
        argv.extend(["--adw-id", request.adw_id])
    if request.models:
        argv.extend(["--models", *request.models])
    argv.extend(request.extra)
    return subprocess.run(argv, cwd=Path.cwd()).returncode


def require_initialized() -> None:
    config = Path("adws/adw_sssf_config/sssf.config.yaml")
    if not config.is_file():
        raise SystemExit("factory is not initialized here; run `just init`")


def require_clean_git() -> None:
    root = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                          text=True)
    if root.returncode or Path(root.stdout.strip()).resolve() != Path.cwd().resolve():
        raise SystemExit("SDLC modes require the current directory to be a Git repository root")
    dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True,
                           check=True)
    if dirty.stdout.strip():
        raise SystemExit("SDLC modes commit their result; commit or stash existing changes first")


def fusion_models(given: list[str]) -> list[str]:
    models = given or os.environ.get("SSSF_FUSION_MODELS", "").split()
    if not models and sys.stdin.isatty():
        models = input("Fusion models (3-5 provider/model IDs, space separated): ").split()
    if not 3 <= len(models) <= 5:
        raise SystemExit("Fusion requires 3-5 models; pass --model three to five times")
    return models


def latest_plan(adw_id: str) -> Path:
    plans = sorted(Path(f"adws/adw_data/sessions/{adw_id}/context_handoff").glob(
        "fusion_*/plan_*.md"))
    if not plans:
        raise SystemExit("Fusion finished without a plan artifact")
    return plans[-1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=MODES)
    parser.add_argument("prompt", nargs="?")
    parser.add_argument("--config", default="adws/adw_sssf_config/sssf.config.yaml")
    parser.add_argument("--model", action="append", default=[], help="Fusion model; repeat 3-5 times")
    parser.add_argument("--yes", action="store_true", help="accept SSDLC human gates (CI only)")
    args = parser.parse_args()

    require_initialized()
    mode = args.mode or choose("Mode", list(MODES))
    prompt = args.prompt or input("Request: ").strip()
    if not prompt:
        raise SystemExit("request cannot be empty")

    if mode in {"sdlc", "ssdlc"}:
        require_clean_git()
    if mode == "fusion":
        return run(Workflow(MODES[mode], prompt, args.config,
                            models=fusion_models(args.model)))
    if mode != "ssdlc":
        return run(Workflow(MODES[mode], prompt, args.config))

    models = fusion_models(args.model)
    adw_id = f"ssdlc-{secrets.token_hex(4)}"
    code = run(Workflow(MODES["fusion"], prompt, args.config,
                        adw_id=adw_id, models=models))
    if code:
        return code
    plan = latest_plan(adw_id)
    print(f"\nFusion plan: {plan}\n")
    print(plan.read_text())
    if not args.yes and input("\nApprove this plan and start implementation? [y/N] ").strip().lower() not in {"y", "yes"}:
        print("Stopped before implementation. Revise the request and run `just go ssdlc` again.")
        return 2
    extra = ["--approved-plan", str(plan)]
    if args.yes:
        extra.append("--yes")
    return run(Workflow(MODES["ssdlc"], prompt, args.config,
                        adw_id=adw_id, extra=extra))


if __name__ == "__main__":
    sys.exit(main())
