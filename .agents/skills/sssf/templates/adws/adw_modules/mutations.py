"""Execute reviewed faults in disposable copies; never mutate the working tree.

The project owns its test command in quality.py. Each probe must fail with its
reviewed assertion marker; crashes, collection failures and timeouts are not kills.
"""

import ast
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import permissions, quality
from .data_types import GateReport, MutationCase, QualityResult, TestReviewOutput


def validate_cases(envelope: TestReviewOutput, run) -> GateReport:
    """A fault must change exactly one production fragment inside this repo."""
    report = GateReport().check("mutations", bool(envelope.mutations) or not envelope.approved,
                                "approved tests need at least one behavioral fault probe")
    writer = next(a for a in run.cfg.agents if a.name == "test_writer")
    for case in envelope.mutations:
        try:
            path = Path(case.path)
            root = Path(run.repo_root).resolve()
            if not path.parts or path.is_absolute() or ".." in path.parts:
                raise ValueError("use a repo-relative production path")
            target = root / path
            target.resolve().relative_to(root)
            if target.is_symlink() or permissions.permitted(path.as_posix(), writer, run.cfg):
                raise ValueError("mutate production logic, not tests, runtime, or symlinks")
            if path.parts[0] in {".git", ".claude", ".codex", ".agents"}:
                raise ValueError("do not mutate harness metadata")
            source = target.read_text()
            if source.count(case.before) != 1 or case.before == case.after:
                raise ValueError("before must match exactly once and after must differ")
            if target.suffix == ".py":
                ast.parse(source.replace(case.before, case.after, 1))
            report.check(case.path, True, case.reason)
        except (OSError, ValueError, SyntaxError) as error:
            report.check(case.path, False, str(error))
    return report


def _copy_project(root: Path, destination: Path) -> None:
    """Copy Git-visible files, including new tests, without sharing writable files."""
    result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                            cwd=root, capture_output=True, text=True, check=True)
    for name in set(result.stdout.split("\0")) - {""}:
        source = root / name
        if not source.exists():
            continue                           # tracked file deleted by this change
        if source.is_symlink():
            # Linked engine machinery: the sandbox runs the project's tests,
            # never the engine, so these stay out. Any other external link
            # (credentials, data) is still refused, not copied.
            if permissions.is_engine_link(name):
                continue
            source.resolve().relative_to(root)  # no copying external credentials/data
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    # Node resolves packages relative to cwd. Copies deliberately don't share
    # writable dependencies; Python projects normally resolve through uv run.
    for packages in root.glob("**/node_modules"):
        if ".git" not in packages.parts and not any(p == "node_modules" for p in packages.relative_to(root).parts[:-1]):
            shutil.copytree(packages, destination / packages.relative_to(root), dirs_exist_ok=True)


def run_mutations(run, cases: list[MutationCase]) -> QualityResult:
    """Require green baseline → assertion failure for every fault → green restoration."""
    if not cases:
        return QualityResult(passed=False, failures=["no behavioral mutation probes supplied"])
    review = TestReviewOutput(status="success", approved=True, mutations=cases)
    validity = validate_cases(review, run)
    if not validity.passed:
        return QualityResult(passed=False, failures=validity.violations)
    checks = []
    with tempfile.TemporaryDirectory(prefix="sssf-mutations-") as temporary:
        workspace = Path(temporary)
        _copy_project(Path(run.repo_root).resolve(), workspace)
        baseline = quality.run_tests(run, workspace, "mutation_baseline")
        checks.extend(baseline.checks)
        if not baseline.checks:
            return QualityResult(passed=False, failures=["test suite reported no checks"])
        if not baseline.passed:
            return quality._aggregate(checks)
        baseline_log = "\n".join(Path(path).read_text() for path in baseline.artifacts)
        for index, case in enumerate(cases, 1):
            target = workspace / case.path
            original = target.read_bytes()
            try:
                target.write_text(original.decode().replace(case.before, case.after, 1))
                result = quality.run_tests(run, workspace, f"mutation_{index}")
                if not result.checks:
                    return QualityResult(passed=False, checks=checks, failures=["mutation suite reported no checks"])
                # Read the whole log: the assertion may precede a long summary.
                log = "\n".join(Path(path).read_text() for path in result.artifacts)
                invalid = any(marker in log for marker in (
                    "SyntaxError", "ImportError", "ModuleNotFoundError", "ERROR collecting"))
                failed = [check for check in result.checks if not check.passed]
                killed = (bool(failed) and all(check.returncode == 1 for check in failed) and case.failure_marker in log
                          and case.failure_marker not in baseline_log and not invalid)
                for check in result.checks:
                    checks.append(check.model_copy(update={
                        "passed": killed,
                        "output_tail": f"{'killed' if killed else 'survived or invalid'}: {case.reason}\n{check.output_tail}"}))
                run.console.note(f"mutation {index}: {'killed' if killed else 'survived or invalid'} — {case.reason}")
            finally:
                target.write_bytes(original)
        checks.extend(quality.run_tests(run, workspace, "mutation_restored").checks)
    return quality._aggregate(checks)
