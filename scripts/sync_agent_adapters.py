#!/usr/bin/env python3
"""Sync tool-specific agent adapters from the shared .agents layer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = ROOT / ".agents"
GENERATED_NOTE = (
    "<!-- Generated from {source}. Do not edit directly. "
    "Run `uv run python scripts/sync_agent_adapters.py --write`. -->"
)
GENERATED_MARKER = "Generated from .agents/"
REQUIRED_SOURCE_DIRS = ["rules", "skills", "agents", "workflows"]


class DriftError(Exception):
    """Raised when a generated adapter is missing or out of date."""


class SourceRule:
    """Parsed shared rule file."""

    def __init__(self, source_path: Path, paths: list[str], body: str) -> None:
        self.source_path = source_path
        self.paths = paths
        self.body = body


class GeneratedFile:
    """Expected generated file content."""

    def __init__(self, path: Path, content: str) -> None:
        self.path = path
        self.content = content


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def normalize_text(text: str) -> str:
    return text.rstrip() + "\n"


def generated_note(source_path: Path) -> str:
    return GENERATED_NOTE.format(source=relative(source_path))


def split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        return "", text

    end_marker = "\n---\n"
    end_index = text.find(end_marker, 4)
    if end_index == -1:
        return "", text

    frontmatter = text[4:end_index]
    body = text[end_index + len(end_marker) :]
    return frontmatter, body


def parse_paths(frontmatter: str) -> list[str]:
    paths: list[str] = []
    in_paths = False

    for raw_line in frontmatter.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped == "paths:":
            in_paths = True
            continue
        if in_paths and stripped.startswith("- "):
            paths.append(stripped[2:].strip().strip('"'))
            continue
        if in_paths and stripped and not raw_line.startswith(" "):
            in_paths = False

    return paths


def add_generated_note(text: str, source_path: Path) -> str:
    note = generated_note(source_path)
    frontmatter, body = split_frontmatter(text)
    if frontmatter:
        return normalize_text(f"---\n{frontmatter}\n---\n\n{note}\n\n{body.lstrip()}")
    return normalize_text(f"{note}\n\n{text.lstrip()}")


def load_rule(path: Path) -> SourceRule:
    text = normalize_text(read_text(path))
    frontmatter, body = split_frontmatter(text)
    paths = parse_paths(frontmatter)
    return SourceRule(path, paths, body)


def iter_files(base: Path, pattern: str) -> list[Path]:
    if not base.exists():
        return []
    return sorted(base.glob(pattern))


def validate_source_layer() -> None:
    if not AGENTS_DIR.is_dir():
        raise DriftError(
            f"Missing shared agent source directory: {relative(AGENTS_DIR)}"
        )

    missing_dirs = [
        name for name in REQUIRED_SOURCE_DIRS if not (AGENTS_DIR / name).is_dir()
    ]
    if missing_dirs:
        joined = ", ".join(f".agents/{name}" for name in missing_dirs)
        raise DriftError(f"Missing required shared agent source directories: {joined}")

    source_patterns = ["rules/*.md", "skills/*/SKILL.md", "agents/*.md"]
    source_count = sum(
        len(iter_files(AGENTS_DIR, pattern)) for pattern in source_patterns
    )
    if source_count == 0:
        raise DriftError("No generated adapter source files found under .agents/.")


def cursor_frontmatter(rule: SourceRule) -> str:
    description = f"Shared rule from {relative(rule.source_path)}"
    if not rule.paths:
        return f'---\ndescription: "{description}"\nalwaysApply: true\n---'

    globs = "\n".join(f"  - {path}" for path in rule.paths)
    return (
        f'---\ndescription: "{description}"\nglobs:\n{globs}\nalwaysApply: false\n---'
    )


def cursor_rule_content(rule: SourceRule) -> str:
    note = generated_note(rule.source_path)
    body = rule.body.lstrip()
    return normalize_text(f"{cursor_frontmatter(rule)}\n\n{note}\n\n{body}")


def claude_rule_files() -> list[GeneratedFile]:
    files: list[GeneratedFile] = []
    for source_path in iter_files(AGENTS_DIR / "rules", "*.md"):
        content = add_generated_note(read_text(source_path), source_path)
        files.append(
            GeneratedFile(ROOT / ".claude" / "rules" / source_path.name, content)
        )
    return files


def claude_skill_files() -> list[GeneratedFile]:
    files: list[GeneratedFile] = []
    for entrypoint in iter_files(AGENTS_DIR / "skills", "*/SKILL.md"):
        skill_dir = entrypoint.parent
        for source_path in sorted(skill_dir.rglob("*")):
            if not source_path.is_file() or any(
                part in {"__pycache__", ".ruff_cache", ".pytest_cache"}
                for part in source_path.relative_to(skill_dir).parts
            ):
                continue
            content = read_text(source_path)
            if source_path == entrypoint:
                content = add_generated_note(content, source_path)
            files.append(GeneratedFile(
                ROOT / ".claude" / "skills" / skill_dir.name
                / source_path.relative_to(skill_dir), content,
            ))
    return files


def claude_agent_files() -> list[GeneratedFile]:
    files: list[GeneratedFile] = []
    for source_path in iter_files(AGENTS_DIR / "agents", "*.md"):
        content = add_generated_note(read_text(source_path), source_path)
        files.append(
            GeneratedFile(ROOT / ".claude" / "agents" / source_path.name, content)
        )
    return files


def cursor_rule_files() -> list[GeneratedFile]:
    files: list[GeneratedFile] = []
    for source_path in iter_files(AGENTS_DIR / "rules", "*.md"):
        rule = load_rule(source_path)
        target_name = source_path.with_suffix(".mdc").name
        files.append(
            GeneratedFile(
                ROOT / ".cursor" / "rules" / target_name, cursor_rule_content(rule)
            )
        )
    return files


def expected_files() -> list[GeneratedFile]:
    validate_source_layer()
    return [
        *claude_rule_files(),
        *claude_skill_files(),
        *claude_agent_files(),
        *cursor_rule_files(),
    ]


def managed_adapter_files() -> list[Path]:
    managed_patterns = [
        (ROOT / ".claude" / "rules", "*.md"),
        (ROOT / ".claude" / "skills", "*/SKILL.md"),
        (ROOT / ".claude" / "agents", "*.md"),
        (ROOT / ".cursor" / "rules", "*.mdc"),
    ]

    files: list[Path] = []
    for base, pattern in managed_patterns:
        files.extend(iter_files(base, pattern))
    return sorted(files)


def is_generated_adapter(path: Path) -> bool:
    return path.is_file() and GENERATED_MARKER in read_text(path)


def stale_generated_files(files: list[GeneratedFile]) -> list[Path]:
    expected_paths = {generated_file.path for generated_file in files}
    return [
        path
        for path in managed_adapter_files()
        if path not in expected_paths and is_generated_adapter(path)
    ]


def remove_stale_generated_files(files: list[GeneratedFile]) -> None:
    for path in stale_generated_files(files):
        path.unlink()


def write_expected_files(files: list[GeneratedFile]) -> None:
    for generated_file in files:
        write_text(generated_file.path, generated_file.content)
    remove_stale_generated_files(files)


def check_expected_files(files: list[GeneratedFile]) -> None:
    problems: list[str] = []
    for generated_file in files:
        if not generated_file.path.exists():
            problems.append(f"missing: {relative(generated_file.path)}")
            continue
        actual = read_text(generated_file.path)
        if actual != generated_file.content:
            problems.append(f"out of date: {relative(generated_file.path)}")

    for path in stale_generated_files(files):
        problems.append(f"stale generated adapter: {relative(path)}")

    if problems:
        joined = "\n".join(problems)
        raise DriftError(
            "Agent adapters are not in sync with .agents/. "
            "Run `uv run python scripts/sync_agent_adapters.py --write`.\n"
            f"{joined}"
        )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync generated agent adapters from .agents/."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write generated adapters")
    mode.add_argument("--check", action="store_true", help="check generated adapters")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    files = expected_files()

    if args.write:
        write_expected_files(files)
        sys.stdout.write(
            f"Synced {len(files)} generated adapter files from .agents/.\n"
        )
        return 0

    try:
        check_expected_files(files)
    except DriftError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1

    sys.stdout.write(f"All {len(files)} generated agent adapter files are in sync.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
