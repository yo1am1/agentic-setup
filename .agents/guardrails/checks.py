#!/usr/bin/env python3
"""Run repository checks on immutable Git snapshots."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / ".agents/guardrails/policy.json").read_text())
PYTHON_PATHS = POLICY["python_paths"]


def git(*args, env=None, input_text=None):
    return subprocess.run(["git", *args], cwd=ROOT, env=env, input=input_text,
                          text=True, capture_output=True, check=True).stdout.strip()


def changed_paths(base, target):
    return git("diff", "--name-only", "-z", base, target).split("\0") if base else git(
        "ls-tree", "-r", "--name-only", "-z", target
    ).split("\0")


def requires_python(paths):
    return any(path.endswith(".py") or Path(path).name in {"pyproject.toml", "uv.lock"} for path in paths)


def zero_oid(oid):
    return len(oid) in {40, 64} and set(oid) == {"0"}


def snapshot(tree, destination):
    index = Path(destination).parent / (Path(destination).name + ".index")
    env = os.environ | {"GIT_INDEX_FILE": str(index)}
    try:
        git("read-tree", tree, env=env)
        subprocess.run(["git", "checkout-index", "--all", f"--prefix={destination}/"],
                       cwd=ROOT, env=env, check=True, capture_output=True)
    finally:
        index.unlink(missing_ok=True)


def run_checks(tree, paths):
    with tempfile.TemporaryDirectory(prefix="guardrails-") as temp:
        snapshot(tree, temp)
        repo = Path(temp)
        try:
            policy = json.loads((repo / ".agents/guardrails/policy.json").read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Cannot load snapshot check policy: {exc}", file=sys.stderr)
            return False
        commands = []
        if requires_python(paths):
            commands.extend(policy["project_checks"])
        if any(p.startswith(".agents/guardrails/") for p in paths):
            commands.append(policy["guardrail_tests"])
        env = os.environ | {"UV_PROJECT_ENVIRONMENT": str(repo / ".venv")}
        env.pop("VIRTUAL_ENV", None)
        for command in commands:
            print("+", " ".join(command), flush=True)
            try:
                subprocess.run(command, cwd=repo, env=env, check=True)
            except (OSError, subprocess.CalledProcessError) as exc:
                print(f"Required check failed or unavailable: {' '.join(command)} ({exc})", file=sys.stderr)
                return False
        return True


def authorized():
    if os.environ.get("GUARDRAILS_AUTHORIZED") != "1":
        print("Set GUARDRAILS_AUTHORIZED=1 only after authorizing this commit or push.", file=sys.stderr)
        return False
    return True


def pre_commit():
    if not authorized():
        return 1
    tree = git("write-tree")
    paths = git("diff", "--cached", "--name-only", "--no-renames", "-z").split("\0")
    paths = [p for p in paths if p]
    if not run_checks(tree, paths):
        return 1
    if git("write-tree") != tree:
        print("Index changed while checks ran; rerun pre-commit.", file=sys.stderr)
        return 1
    return 0


def pre_push(input_text):
    if not authorized():
        return 1
    rows = [line.split() for line in input_text.splitlines() if line.strip()]
    if not rows:
        print("No outgoing refs received; cannot validate push.", file=sys.stderr)
        return 1
    for row in rows:
        if len(row) != 4:
            print("Malformed pre-push ref tuple.", file=sys.stderr)
            return 1
        local_ref, local_oid, remote_ref, remote_oid = row
        if zero_oid(local_oid):
            print(f"Deletion {remote_ref}: authorize and review separately; no outgoing tree.")
            continue
        try:
            commit = git("rev-parse", "--verify", f"{local_oid}^{{commit}}")
            tree = git("rev-parse", "--verify", f"{commit}^{{tree}}")
            base = None
            if not zero_oid(remote_oid):
                remote = git("rev-parse", "--verify", f"{remote_oid}^{{commit}}")
                merge = subprocess.run(["git", "merge-base", remote, commit], cwd=ROOT,
                                       text=True, capture_output=True)
                base = merge.stdout.strip() if merge.returncode == 0 else None
            paths = changed_paths(base, commit)
        except subprocess.CalledProcessError as exc:
            print(f"Cannot resolve comparison for {local_ref} -> {remote_ref}: {exc}", file=sys.stderr)
            return 1
        paths = [p for p in paths if p]
        if not run_checks(tree, paths):
            return 1
        try:
            current = git("rev-parse", "--verify", f"{local_ref}^{{commit}}")
        except subprocess.CalledProcessError:
            current = ""
        if current != commit:
            print(f"Outgoing ref {local_ref} changed while checks ran; rerun pre-push.", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"pre-commit", "pre-push"}:
        raise SystemExit("usage: checks.py pre-commit|pre-push")
    raise SystemExit(pre_commit() if sys.argv[1] == "pre-commit" else pre_push(sys.stdin.read()))
