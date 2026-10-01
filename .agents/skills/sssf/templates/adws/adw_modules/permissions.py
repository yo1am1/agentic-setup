"""What an agent may CHANGE, enforced in code after the fact.

`tools:` is a capability list, not a sandbox, and two holes make it
unenforceable on its own:

  * `bash` runs anything. A builder handed bash to run a test suite can also
    run `git checkout adws/` — which is not hypothetical: one did, discarding
    uncommitted changes to the very quality check it was about to be judged by.
  * `write` reaches any path, not just the one report file an agent was given
    it for. A reviewer configured with "no edit, so it cannot quietly fix"
    could still rewrite the code it was reviewing.

So permission is verified the way every other claim in this system is —
after the fact, against the repo itself. `snapshot()` fingerprints the working
tree's change-set before an agent runs; `enforce()` compares it afterwards and
fails the phase if the agent touched anything outside its allowlist.

Comparing change-sets, rather than watching for writes, is what catches the
`git checkout` case: a path that was modified before the agent ran and is clean
afterwards has been reverted, and a reversion is a modification. Appearing,
disappearing, and changing all count.

A breach is NOT a gate violation. Gates are for work an agent can be asked to
redo; a breach cannot be corrected by re-prompting, because the write already
happened. It aborts the phase and names every offending path.

Two keys drive it, both in sssf.config.yaml:
    defaults.protected_files   paths no agent may touch unless it names them itself
    agents[].writes      None = unrestricted · [] = read-only · [...] = only these
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import threading
from pathlib import Path, PurePosixPath

from .data_types import AgentConfig, FileSnapshot, SSSFConfig

# `git` is one process per repository, and this module both reads the working
# tree and rolls parts of it back. Fusion runs a round of seats concurrently,
# each bracketed by its own snapshot/enforce, so those git invocations have to
# take turns — two `git checkout --` calls interleaving is the destructive
# version of the very problem this module exists to prevent.
#
# Concurrency is not lost to this: a snapshot of a clean tree is milliseconds
# against agent turns measured in minutes. It is also the reason Fusion refuses
# to parallelise seats that are not read-only (see fusion.parallel_safe): with
# every participant at `writes: []` the allowlist is empty for all of them, so
# per-agent and per-round enforcement roll back exactly the same paths and the
# only thing concurrency costs is the name in the error message.
_GIT_LOCK = threading.Lock()


class PermissionBreach(RuntimeError):
    """An agent modified a path it was not permitted to modify."""


def is_engine_link(name: str) -> bool:
    """True for repo-relative names install.py manages as symlinks into the
    shared engine checkout (LINK_DIRS/LINK_GLOBS/LINK_FILES there). Machinery,
    never project content — identified by name, not by where the link resolves,
    because the engine may be running from either the live checkout or the
    skill's templates."""
    parts = PurePosixPath(name).parts
    if not parts:
        return False
    if parts[0] != "adws":
        return name in {"justfile", ".env.sample", ".agents/skills/sssf"}
    if len(parts) < 2:
        return False
    return (parts[1] in {"adw_modules", "adw_sssf_config", "conftest.py"}
            or parts[1].startswith("adw_")
            or parts[1:3] == ("adw_data", "prompt_engineering")
            or parts[1:3] == ("adw_data", "harness_engineering"))


def _git(args: list[str], cwd) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise PermissionBreach(f"cannot inspect working tree: {result.stderr.strip()}")
    return result.stdout


def snapshot(run) -> dict[str, FileSnapshot]:
    """Fingerprint every path the working tree currently differs on.

    Store contents, not line counts: same-size edits and rewritten untracked
    tests must register, and an unauthorized edit must be recoverable.
    Gitignored paths never appear, which is why the session runtime under
    `data_dir` — where handoff files legitimately land — needs no special case.
    """
    with _GIT_LOCK:
        dirty = set(_git(["diff", "HEAD", "--name-only", "-z"], run.repo_root).split("\0"))
        untracked = set(_git(["ls-files", "--others", "--exclude-standard", "-z"],
                            run.repo_root).split("\0"))
    fingerprints = {}
    for name in (dirty | untracked) - {""}:
        path = Path(run.repo_root) / name
        link = path.is_symlink()
        present = link or path.exists()
        fingerprints[name] = FileSnapshot(
            content=(os.fsencode(os.readlink(path)) if link else path.read_bytes()) if present else None,
            symlink=link, mode=stat.S_IMODE(path.lstat().st_mode) if present else 0o644,
            untracked=name in untracked)
    return fingerprints


def changed_paths(before: dict[str, FileSnapshot], after: dict[str, FileSnapshot]) -> list[str]:
    """Every path whose state differs — appeared, vanished, or was rewritten."""
    return sorted({p for p in set(before) | set(after)
                   if before.get(p) != after.get(p)})


def _glob(pattern: str) -> re.Pattern:
    """Translate a pattern, with `*` stopping at a path separator.

    fnmatch would let `*` cross `/`, which quietly widens every pattern:
    `adws/adw_*.py` would match `adws/adw_data/sessions/x/y.py` as well as the
    ADW scripts it means. `**` is the way to say "cross directories".
    """
    out, i = [], 0
    while i < len(pattern):
        char = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif char == "*":
            out.append("[^/]*")
            i += 1
        elif char == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(char))
            i += 1
    return re.compile("".join(out))


def _matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/"):                      # directory prefix
        return path.startswith(pattern)
    if "*" in pattern or "?" in pattern:
        return _glob(pattern).fullmatch(path) is not None
    return path == pattern


def always_writable(cfg: SSSFConfig) -> list[str]:
    """The session runtime, which EVERY agent must be able to write.

    `context_handoff/` is the one place agents hand work to each other, and an
    agent's own prompts, raw_output.jsonl, and envelope.json land beside it.
    Scout writes its findings there, the reviewer its review, the planner its
    plan — a read-only agent is read-only with respect to the REPO, never with
    respect to its own report.

    This is granted from `data_dir` rather than left to .gitignore. The runtime
    is normally ignored, so it never even appears in a snapshot — but an agent's
    ability to record its work must not hang on a gitignore entry that someone
    can delete or that a changed `data_dir` can outgrow.
    """
    return [cfg.defaults.data_dir.rstrip("/") + "/"]


def permitted(path: str, agent: AgentConfig, cfg: SSSFConfig) -> bool:
    """Session runtime first, then the agent's own list, then what is protected."""
    if any(_matches(path, p) for p in always_writable(cfg)):
        return True
    if any(_matches(path, p) for p in (agent.writes or [])):
        return True                      # naming a path is what unlocks a protected one
    if any(_matches(path, p) for p in cfg.defaults.protected_files):
        return False
    return agent.writes is None          # None = unrestricted, [] = no repo writes


def _roll_back(run, path: str, before: dict[str, FileSnapshot], after: dict[str, FileSnapshot]) -> str:
    """Undo one unauthorized change. Returns a word describing what happened.

    Restore dirty files from their saved contents, including untracked tests.
    Clean tracked files can still be restored from HEAD.
    """
    target = Path(run.repo_root) / path
    if path in before:
        saved = before[path]
        try:
            # Refuse a redirected parent: restore only into the repo, or through
            # an engine link — that is how a tampered shared file is repaired.
            if not (target.parent.resolve().is_relative_to(Path(run.repo_root).resolve())
                    or is_engine_link(path)):
                raise ValueError(f"{target.parent} escapes both the repo and the engine")
            target.unlink(missing_ok=True)
            if saved.content is not None:
                target.parent.mkdir(parents=True, exist_ok=True)
                if saved.symlink:
                    target.symlink_to(os.fsdecode(saved.content))
                else:
                    target.write_bytes(saved.content)
                    target.chmod(saved.mode)
            return "restored pre-agent contents"
        except (OSError, ValueError) as error:
            return f"could not restore ({error})"
    if path in after and after[path].untracked:
        try:
            (Path(run.repo_root) / path).unlink()
            return "deleted"
        except OSError as error:
            return f"could not delete ({error})"
    with _GIT_LOCK:
        result = subprocess.run(["git", "checkout", "--", path],
                                cwd=run.repo_root, capture_output=True, text=True)
    return "rolled back" if result.returncode == 0 else "could not roll back"


def enforce(run, phase, agent: AgentConfig, before: dict[str, FileSnapshot]) -> list[str]:
    """Compare the tree against `before`; undo and raise if the agent overstepped.

    Returns the paths it legitimately changed, so the trace records what an
    agent actually touched rather than only what it claimed in its envelope.

    Detection alone would leave the repo holding the unauthorized change while
    reporting a failure, so anything the agent introduced outside its allowlist
    is rolled back before the phase dies. What it cannot undo, it names.
    """
    after = snapshot(run)
    touched = changed_paths(before, after)
    breaches = [p for p in touched if not permitted(p, agent, run.cfg)]
    if not breaches:
        return touched

    outcomes = {p: _roll_back(run, p, before, after) for p in breaches}
    scope = ("read-only" if agent.writes == []
             else f"limited to {agent.writes}" if agent.writes
             else f"barred from {run.cfg.defaults.protected_files}")
    detail = "\n".join(f"  - {p} — {outcome}" for p, outcome in outcomes.items())
    raise PermissionBreach(
        f"{agent.name} is {scope} but modified {len(breaches)} path(s):\n{detail}")
