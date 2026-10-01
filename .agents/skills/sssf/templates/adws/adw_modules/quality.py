"""Run the repo's configured static checks and tests without a shell.

Commands live in adws/adw_sssf_config/quality.json. `just init` detects common
project scripts, and the test writer may add the test command for a greenfield
project. Missing or fake commands fail closed; they never count as verification.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import time
from pathlib import Path

from .data_types import (EventRecord, QualityCheckResult, QualityCheckSpec,
                         QualityResult, VerifyOutput)
from .utils import now_iso, operator_env

TAIL_CHARS = 4_000
CONFIG = "adws/adw_sssf_config/quality.json"
FAKE_COMMANDS = {"echo", "false", "printf", "true"}


def _check_dir(run, name: str) -> Path:
    seq = run.phases[-1].seq if run.phases else 0
    path = run.context_handoff_dir / "quality" / f"{seq:02d}_{name}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _specs(run, group: str) -> list[QualityCheckSpec]:
    path = Path(run.repo_root) / CONFIG
    try:
        raw = json.loads(path.read_text())
        rows = raw[group]
        specs = [QualityCheckSpec(**row) for row in rows]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(f"invalid {CONFIG}: {error}") from error
    if not specs:
        raise RuntimeError(f"no {group} commands configured in {CONFIG}; run `just init` and review it")
    fake = [spec.name for spec in specs if not spec.argv or Path(spec.argv[0]).name in FAKE_COMMANDS]
    if fake:
        raise RuntimeError(f"{CONFIG} contains non-verifying {group} commands: {', '.join(fake)}")
    return specs


def _run(spec: QualityCheckSpec, run, cwd: Path | None = None) -> QualityCheckResult:
    phase = run.phases[-1]
    output_artifact = _check_dir(run, spec.name) / "command.log"
    command = shlex.join(spec.argv)
    env = operator_env()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    run.console.note(f"quality {spec.name}: {command}")
    started_at = now_iso()
    clock = time.monotonic()
    stdout = stderr = ""
    try:
        completed = subprocess.run(spec.argv, cwd=cwd or run.repo_root, env=env,
                                   capture_output=True, text=True,
                                   timeout=spec.timeout_seconds)
        returncode, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as error:
        returncode = 124
        stdout, stderr = error.stdout or "", error.stderr or ""
        stdout = stdout.decode(errors="replace") if isinstance(stdout, bytes) else stdout
        stderr = stderr.decode(errors="replace") if isinstance(stderr, bytes) else stderr
        stderr += f"\nTimed out after {spec.timeout_seconds}s."
    except OSError as error:
        returncode, stderr = 127, str(error)
    duration = time.monotonic() - clock
    output_artifact.write_text(
        f"$ {command}\nexit: {returncode}\nduration_seconds: {duration:.3f}\n"
        f"\n--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}\n")
    passed = returncode == 0
    run.tracer.event(EventRecord(
        adw_id=run.adw_id, phase_id=phase.phase_id, type="tool_call",
        name=f"quality:{spec.name}",
        payload={"area": spec.area, "operation": spec.operation, "command": command,
                 "returncode": returncode, "passed": passed,
                 "output_artifact": str(output_artifact)},
        started_at=started_at, ended_at=now_iso()))
    run.console.note(f"quality {spec.name}: {'passed' if passed else 'failed'} "
                     f"(exit {returncode}, {duration:.1f}s)")
    return QualityCheckResult(
        name=spec.name, area=spec.area, operation=spec.operation, command=command,
        returncode=returncode, passed=passed, duration_seconds=duration,
        output_artifact=str(output_artifact), output_tail=(stdout + stderr)[-TAIL_CHARS:])


def _aggregate(checks: list[QualityCheckResult]) -> QualityResult:
    failures = [f"{c.name}: `{c.command}` exited {c.returncode}\n{c.output_tail}".rstrip()
                for c in checks if not c.passed]
    return QualityResult(passed=not failures, checks=checks, failures=failures,
                         artifacts=[c.output_artifact for c in checks])


def run_static_quality(run) -> QualityResult:
    return _aggregate([_run(spec, run) for spec in _specs(run, "static")])


def run_tests(run, cwd: Path | None = None, name: str = "test") -> QualityResult:
    specs = [spec.model_copy(update={"name": f"{name}_{spec.name}"})
             for spec in _specs(run, "tests")]
    return _aggregate([_run(spec, run, cwd) for spec in specs])


def run_quality(run) -> QualityResult:
    return _aggregate([*run_static_quality(run).checks, *run_tests(run).checks])


def as_envelope(result: QualityResult, what: str) -> VerifyOutput:
    return VerifyOutput(
        status="success" if result.passed else "fail",
        summary=(f"{what}: all {len(result.checks)} check(s) passed" if result.passed
                 else f"{what}: {len(result.failures)} of {len(result.checks)} check(s) failed"),
        artifacts=result.artifacts,
        notes_for_next_agent=("" if result.passed else
                              "Fix every failure below; command output is authoritative."),
        passed=result.passed, failures=result.failures)
