#!/usr/bin/env -S uv run
# /// script
# dependencies = []
# ///
"""/install — link a repo to the shared SSSF engine. Idempotent.

Usage:
    uv run <skill>/scripts/install.py [--force] [--copy]

Shared machinery — workflow scripts and modules, prompts, harness extensions,
base rosters, the justfile — is symlinked to the software-factory checkout that
owns this skill. Every initialized factory therefore runs the same code and the
same base config: update the software-factory once and every linked repo
follows, with no sync step.

Repo-owned state stays local and real: quality.json (detected per repo), .env,
adw_data/sessions/ and the trace DB.

Existing real files are never replaced silently: they are reported and skipped
until --force. --copy stamps real files instead of links, for a repo that must
keep working even if the software-factory checkout moves or is deleted.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent      # .claude/skills/sssf
MASTER = SKILL.parents[2]                           # the software-factory checkout

# One source of truth, edited in exactly one place: the master's live files.
LINK_DIRS = ["adws/adw_modules",
             "adws/adw_data/prompt_engineering",
             "adws/adw_data/harness_engineering",
             # The .agents/skills convention pi and DeepSeek Harness both scan
             # for project skills, so either can launch ADWs via its own bash
             # tool without extra config — see cookbooks/run_adw.md.
             ".agents/skills/sssf"]
LINK_GLOBS = [("adws", "adw_*.py"), ("adws", "conftest.py"), ("adws/adw_sssf_config", "*.yaml")]
LINK_FILES = ["justfile", ".env.sample"]

GITIGNORE_ENTRIES = [
    "adws/adw_data/sessions/",
    "adws/adw_data/sssf.db*",
    ".env",
    # The ADWs are Python, so importing adw_modules writes bytecode next to it.
    # Chains that end in a commit phase call `git add -A`, so without this a
    # stamped repo commits its own .pyc files — 15 of them showed up in the
    # first repo that was ever installed into from scratch.
    "__pycache__/",
    "*.pyc",
]


def link(src: Path, dest: Path, force: bool, linked: list, skipped: list) -> None:
    """Symlink dest -> src. A correct link is left alone; a wrong one is repaired;
    a real file or directory is replaced only under --force (drifted copies are
    the whole reason to re-run this, but deleting them is still the operator's
    call)."""
    if dest.is_symlink():
        if dest.resolve() == src:
            skipped.append(f"{dest} (already linked)")
            return
        dest.unlink()
    elif dest.exists():
        if not force:
            skipped.append(f"{dest} (exists; --force replaces with a link)")
            return
        shutil.rmtree(dest) if dest.is_dir() else dest.unlink()
        linked.append(f"{dest} (replaced)")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.symlink_to(src, target_is_directory=src.is_dir())
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.symlink_to(src, target_is_directory=src.is_dir())
    linked.append(str(dest))


def stamp(src: Path, dest: Path, force: bool, stamped: list, skipped: list) -> None:
    if src.is_dir():
        for child in sorted(src.iterdir()):
            if child.name == "__pycache__":
                continue
            stamp(child, dest / child.name, force, stamped, skipped)
        return
    if dest.exists() and not force:
        skipped.append(str(dest))
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    stamped.append(str(dest))


def ensure_gitignore(root: Path, stamped: list) -> None:
    gitignore = root / ".gitignore"
    existing = gitignore.read_text().splitlines() if gitignore.exists() else []
    missing = [e for e in GITIGNORE_ENTRIES if e not in existing]
    if missing:
        with gitignore.open("a") as f:
            f.write("\n# sssf runtime\n" + "\n".join(missing) + "\n")
        stamped.append(f"{gitignore} (+{len(missing)} entries)")


def _manager(root: Path) -> str:
    if (root / "bun.lock").exists() or (root / "bun.lockb").exists():
        return "bun"
    if (root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (root / "yarn.lock").exists():
        return "yarn"
    return "npm"


def detect_quality(root: Path) -> dict:
    """Use project manifests to write real argv commands; unknown means fail closed."""
    static, tests = [], []
    python_files = [*root.glob("*.py"), *root.glob("src/**/*.py"), *root.glob("tests/**/*.py")]
    if python_files or (root / "pyproject.toml").exists():
        static.extend([
            {"name": "python_lint", "area": "backend", "operation": "lint",
             "argv": ["uvx", "ruff", "check", ".", "--exclude", "adws", "--exclude", ".claude"]},
            {"name": "python_build", "area": "backend", "operation": "build",
             "argv": ["uv", "run", "python", "-m", "compileall", "-q", "."]},
        ])
        if any((root / name).exists() for name in ("tests", "test")):
            tests.append({"name": "python_test", "area": "backend", "operation": "build",
                          "argv": ["uv", "run", "--with", "pytest", "pytest", "-q"],
                          "timeout_seconds": 600})

    package = root / "package.json"
    if package.exists():
        try:
            scripts = (json.loads(package.read_text()).get("scripts") or {})
        except (OSError, json.JSONDecodeError):
            scripts = {}
        manager = _manager(root)
        for script, operation in (("lint", "lint"), ("typecheck", "typecheck"), ("build", "build")):
            if script in scripts:
                static.append({"name": f"js_{script}", "area": "frontend", "operation": operation,
                               "argv": [manager, "run", script]})
        if "test" in scripts:
            tests.append({"name": "js_test", "area": "frontend", "operation": "build",
                          "argv": [manager, "run", "test"], "timeout_seconds": 600})
    return {"static": static, "tests": tests}


def ensure_quality(root: Path, stamped: list, skipped: list) -> dict:
    path = root / "adws" / "adw_sssf_config" / "quality.json"
    if path.exists():
        skipped.append(str(path))
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
    quality = detect_quality(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(quality, indent=2) + "\n")
    stamped.append(str(path))
    return quality


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="replace existing real files with links (or fresh copies)")
    parser.add_argument("--copy", action="store_true",
                        help="stamp real files instead of symlinks to the software-factory")
    args = parser.parse_args()

    if not (MASTER / "adws" / "adw_modules").is_dir():
        print(f"error: {MASTER} is not a software-factory checkout — install.py must run "
              "from the SSSF skill inside one", file=sys.stderr)
        return 1

    root = Path.cwd()
    done, skipped = [], []
    place = stamp if args.copy else link
    for rel in LINK_DIRS:
        place(MASTER / rel, root / rel, args.force, done, skipped)
    for folder, pattern in LINK_GLOBS:
        for src in sorted((MASTER / folder).glob(pattern)):
            place(src, root / folder / src.name, args.force, done, skipped)
    for rel in LINK_FILES:
        place(MASTER / rel, root / rel, args.force, done, skipped)
    quality = ensure_quality(root, done, skipped)
    ensure_gitignore(root, done)

    mode = "copied" if args.copy else f"linked to {MASTER}"
    print(f"sssf installed into {root} ({mode})")
    print(f"  {'copied' if args.copy else 'linked'}: {len(done)} file(s)")
    for s in done:
        print(f"    + {s}")
    if skipped:
        print(f"  skipped: {len(skipped)}")
        for s in skipped:
            print(f"    · {s}")
    if not quality.get("tests"):
        print("  warning: no test command detected; SDLC modes fail until "
              "adws/adw_sssf_config/quality.json defines one")
    if not quality.get("static"):
        print("  warning: no static/build command detected; SDLC modes fail until "
              "adws/adw_sssf_config/quality.json defines one")
    print("\nnext steps:")
    print("  1. cp .env.sample .env   # then set the key(s) your roster needs")
    print("  2. open adws/adw_sssf_config/quality.json and check the detected commands")
    print("  3. just go               # start the Software Factory web app")
    return 0


if __name__ == "__main__":
    sys.exit(main())
