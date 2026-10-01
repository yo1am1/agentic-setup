#!/usr/bin/env -S uv run
# /// script
# dependencies = []
# ///
"""/remove — unlink a repo from the shared SSSF engine. The inverse of install.

Usage:
    uv run <skill>/scripts/uninstall.py [--force] [--purge] [--dry-run]

By default this removes only the symlinks install created — the ones that still
point into the software-factory. Anything real is left where it is and named in
the report, because a real file at a linked path is either a `--copy` install or
an edit someone made on purpose, and neither is this command's to throw away.

What is repo-owned survives by default and is listed: quality.json, .env, and
the trace under adw_data (sessions and sssf.db) — a run history nobody can
reconstruct. `--purge` deletes that history too; `--force` removes real files at
the install paths; `--dry-run` reports the plan and changes nothing.
"""

import argparse
import shutil
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent      # .claude/skills/sssf
MASTER = SKILL.parents[2]                           # the software-factory checkout

# Mirrors install.py. Kept as its own list rather than imported: the two scripts
# are a matched pair, and a silent drift between them would leave debris behind.
LINK_DIRS = ["adws/adw_modules",
             "adws/adw_data/prompt_engineering",
             "adws/adw_data/harness_engineering",
             ".agents/skills/sssf"]
LINK_GLOBS = [("adws", "adw_*.py"), ("adws", "conftest.py"), ("adws/adw_sssf_config", "*.yaml")]
LINK_FILES = ["justfile", ".env.sample"]

# Repo-owned state: never touched without --purge, and never touched at all in
# the case of .env, which holds secrets this command has no business deleting.
PURGE_PATHS = ["adws/adw_sssf_config/quality.json", "adws/adw_data"]

# Emptied by removing links; removed only if nothing of the repo's own is left.
PRUNE_DIRS = ["adws/adw_sssf_config", "adws/adw_data", "adws", ".agents/skills", ".agents"]


def plan_targets(root: Path) -> list[Path]:
    """Every path install.py would have placed, in removal order."""
    targets = [root / rel for rel in LINK_DIRS]
    for folder, pattern in LINK_GLOBS:
        source = MASTER / folder
        if source.is_dir():
            targets.extend(root / folder / src.name for src in sorted(source.glob(pattern)))
        # A repo may hold links to files the master has since dropped; catch
        # those too, so removing never leaves a dangling link behind.
        targets.extend(p for p in sorted((root / folder).glob(pattern)) if p not in targets)
    targets.extend(root / rel for rel in LINK_FILES)
    return targets


def ours(path: Path) -> bool:
    """True for a symlink pointing into the software-factory this skill owns."""
    if not path.is_symlink():
        return False
    try:
        target = path.resolve()
    except OSError:
        return False                 # a dangling link we placed is still ours
    return target == MASTER or str(target).startswith(str(MASTER) + "/")


def remove(path: Path, force: bool, dry_run: bool, removed: list, kept: list) -> None:
    if path.is_symlink():
        if not ours(path) and not force:
            kept.append(f"{path} (link to somewhere else)")
            return
        if not dry_run:
            path.unlink()
        removed.append(f"{path} (link)")
        return
    if not path.exists():
        return
    if not force:
        kept.append(f"{path} (real file — use --force)")
        return
    if not dry_run:
        shutil.rmtree(path) if path.is_dir() else path.unlink()
    removed.append(f"{path} (real, forced)")


def prune(root: Path, dry_run: bool, removed: list) -> None:
    """Drop directories the links left empty; anything still holding a file stays."""
    for rel in PRUNE_DIRS:
        path = root / rel
        if not path.is_dir() or path.is_symlink():
            continue
        if any(path.iterdir()):
            continue
        if not dry_run:
            path.rmdir()
        removed.append(f"{path} (empty directory)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="also remove real files at the install paths (a --copy install)")
    parser.add_argument("--purge", action="store_true",
                        help="also delete repo-owned state: quality.json and the whole trace under adw_data")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be removed and change nothing")
    args = parser.parse_args()

    root = Path.cwd().resolve()
    # The master owns the real files every factory links to. Removing them here
    # would break every linked repo at once, so it is refused outright.
    if root == MASTER:
        print(f"error: {root} is the software-factory itself — removing it would break every "
              "factory linked to it", file=sys.stderr)
        return 1

    removed, kept = [], []
    for target in plan_targets(root):
        remove(target, args.force, args.dry_run, removed, kept)

    if args.purge:
        for rel in PURGE_PATHS:
            remove(root / rel, True, args.dry_run, removed, kept)
    else:
        for rel in PURGE_PATHS:
            if (root / rel).exists():
                kept.append(f"{root / rel} (repo-owned — use --purge)")

    prune(root, args.dry_run, removed)
    env = root / ".env"
    if env.exists():
        kept.append(f"{env} (secrets — never removed)")

    verb = "would remove" if args.dry_run else "removed"
    print(f"sssf {'removal plan for' if args.dry_run else 'removed from'} {root}")
    print(f"  {verb}: {len(removed)}")
    for item in removed:
        print(f"    - {item}")
    if kept:
        print(f"  kept: {len(kept)}")
        for item in kept:
            print(f"    · {item}")
    if not removed:
        print("  nothing to remove — this directory is not a linked factory")
    # The entries are inert once the machinery is gone, and rewriting a file the
    # repo owns to delete five lines is a worse trade than leaving them.
    if (root / ".gitignore").exists():
        print("\nadws/.env/__pycache__ entries remain in .gitignore; remove them by hand if you want them gone")
    return 0


if __name__ == "__main__":
    sys.exit(main())
