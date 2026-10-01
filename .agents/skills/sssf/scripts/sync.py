#!/usr/bin/env -S uv run
# /// script
# dependencies = []
# ///
"""/sync — push machinery updates from the skill into every stamped factory.

Usage:
    uv run <skill>/scripts/sync.py [PATH ...] [--apply] [--allow-dirty]

install.py stamps once and then skips every file that already exists, so a
factory installed last week never sees a fix made to the skill this week. Its
only other setting is --force, which install.md warns overwrites ALL stamped
files "including sssf.config.yaml and prompt_engineering/" — the roster and the
prompts an engineer spent the week tuning. That leaves no way to ship a fix to
adw_modules/ without flattening the parts that are theirs.

This is that missing middle: --force narrowed to the machinery.

Reports by default and writes nothing. Pass --apply to write.

Targets default to every factory under SSSF_FACTORIES_ROOT (colon separated
like PATH, default ~/VS), found the way the rest of the system finds them —
depth-1 directories holding adws/adw_*.py, which is the skill's own startup
test. Named PATHs override the search.
"""

import argparse
import filecmp
import os
import shutil
import subprocess
import sys
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
DEFAULT_ROOT = str(Path.home() / "VS")

# Machinery: stamped code no engineer is asked to edit, so the skill stays its
# source. Kept as a list of (template subpath, repo subpath) so a file moving
# house is one line, not a special case.
MACHINERY = [
    ("adws/adw_modules", "adws/adw_modules"),
    ("adws", "adws"),  # the starter adw_*.py chains; nested dirs handled above
]

# Files that live inside machinery directories but belong to the engineer. The
# docs are explicit about this one: update_adw.md says "Wire the real command in
# quality.py first", and quality.py's own banner says REPLACE THE PLACEHOLDER
# COMMANDS. Overwriting it would delete the single edit the system asks every
# stamped repo to make. Reported as drift, never written.
ENGINEER_OWNED = {"adws/adw_modules/quality.py"}

# Left to install.py entirely: the roster, the prompts, the justfile and
# .env.sample are all authored per repo after the stamp.


def is_factory(path: Path) -> bool:
    """The skill's own startup test — a factory is a directory with ADWs in it."""
    return any((path / "adws").glob("adw_*.py"))


def discover(roots: str) -> list[Path]:
    found = []
    for root in roots.split(":"):
        if not root:
            continue
        base = Path(root).expanduser()
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if child.is_dir() and is_factory(child):
                found.append(child)
    return found


def template_files() -> list[tuple[Path, str]]:
    """Every machinery file in the skill, as (source, repo-relative path)."""
    files: dict[str, Path] = {}
    for src_sub, dest_sub in MACHINERY:
        src_dir = TEMPLATES / src_sub
        if not src_dir.is_dir():
            continue
        for src in sorted(src_dir.rglob("*.py")):
            if "__pycache__" in src.parts:
                continue
            rel = f"{dest_sub}/{src.relative_to(src_dir)}"
            files.setdefault(rel, src)
    return [(src, rel) for rel, src in sorted(files.items())]


def dirty(repo: Path) -> bool:
    """Uncommitted changes mean git cannot serve as the undo for --apply."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and bool(out.stdout.strip())


def plan(repo: Path) -> tuple[list, list, list]:
    """Split the work three ways: add, update, and leave-alone-but-say-so."""
    add, update, review = [], [], []
    for src, rel in template_files():
        dest = repo / rel
        if not dest.exists():
            (review if rel in ENGINEER_OWNED else add).append((src, dest, rel))
        elif filecmp.cmp(src, dest, shallow=False):
            continue
        elif rel in ENGINEER_OWNED:
            review.append((src, dest, rel))
        else:
            update.append((src, dest, rel))
    return add, update, review


def sync(repo: Path, apply: bool, allow_dirty: bool) -> tuple[int, int]:
    add, update, review = plan(repo)
    if not (add or update or review):
        print(f"{repo}\n  up to date")
        return 0, 0

    print(repo)
    blocked = apply and not allow_dirty and dirty(repo)
    for _, _, rel in add:
        print(f"  + add     {rel}")
    for _, _, rel in update:
        print(f"  ~ update  {rel}")
    for src, dest, rel in review:
        # Never written: the engineer owns this file. Give them the one command
        # that shows what they would be taking, so the choice is informed.
        print(f"  ! review  {rel}   (yours, not overwritten)")
        print(f"              diff {dest} {src}")

    if not apply:
        return 0, len(review)
    if blocked:
        print("  SKIPPED — uncommitted changes here; commit, stash, or pass --allow-dirty")
        return 0, len(review)

    for src, dest, _ in add + update:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    print(f"  wrote {len(add) + len(update)} file(s)")
    return len(add) + len(update), len(review)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", metavar="PATH",
                        help="factories to sync (default: every one found under the roots)")
    parser.add_argument("--apply", action="store_true",
                        help="write the changes (default: report only)")
    parser.add_argument("--allow-dirty", action="store_true",
                        help="write even where git has uncommitted changes")
    args = parser.parse_args()

    roots = os.environ.get("SSSF_FACTORIES_ROOT", DEFAULT_ROOT)
    if args.paths:
        targets = [Path(p).expanduser().resolve() for p in args.paths]
        for t in targets:
            if not is_factory(t):
                print(f"not a factory (no adws/adw_*.py): {t}", file=sys.stderr)
                return 1
    else:
        targets = discover(roots)

    if not targets:
        print(f"no factories found under {roots}")
        return 0

    print(f"source: {TEMPLATES}")
    print(f"{len(targets)} factor{'y' if len(targets) == 1 else 'ies'}\n")

    written = reviewed = 0
    for repo in targets:
        w, r = sync(repo, args.apply, args.allow_dirty)
        written += w
        reviewed += r
        print()

    if not args.apply:
        print("nothing written. re-run with --apply to write.")
    if reviewed:
        print(f"{reviewed} file(s) marked review: yours to merge, never overwritten.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
