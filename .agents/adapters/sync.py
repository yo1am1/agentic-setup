#!/usr/bin/env python3
"""Install repo-local simple/full guidance using only the standard library."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_NAME = ".agents-sync-manifest.json"
CACHE_DIRS = {"__pycache__", ".ruff_cache", ".pytest_cache"}
# Upstream packaging metadata kept in .agents/skills for provenance. A copied
# `.claude-plugin/` makes Claude Code treat a project skill folder as a plugin.
PACKAGING_DIRS = {".claude-plugin", ".cursor-plugin", ".github"}
SHARED_MANIFEST = ".agents/.optional-sync-manifest.json"
OPTIONAL_NAMES = {"council", "herdr", "cavecrew", "humanizer", "specsmd"}
PRIMARY_HOSTS = ("claude", "codex", "gemini")
MARKDOWN_LINK = re.compile(r"(!?\[[^\]]*\]\()([^)]+)(\))")


@dataclass(frozen=True)
class SyncPlan:
    files: dict[str, bytes]
    executable: set[str]


def iter_skill_dirs(source_root: Path, layout: str) -> list[Path]:
    if layout not in render.LAYOUTS:
        raise ValueError(f"unknown layout: {layout}")
    roots = [source_root / ".agents/skills"]
    if layout == "full":
        roots.append(source_root / ".agents/optional")
    for root in roots:
        safe_path(source_root, root.relative_to(source_root).as_posix())
    return [entry.parent for root in roots for entry in sorted(root.glob("*/SKILL.md"))
            if entry.parent.name in ({"caveman", "caveman-commit", "project-flow"} | (OPTIONAL_NAMES if layout == "full" else set()))]


def collect_skill_tree(skill_dir: Path, prefix: str) -> tuple[dict[str, bytes], set[str]]:
    files: dict[str, bytes] = {}
    executable: set[str] = set()
    if skill_dir.is_symlink() or skill_dir.parent.is_symlink():
        raise ValueError(f"refusing symlink source: {skill_dir}")
    for path in sorted(skill_dir.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"refusing symlink source: {path}")
        if not path.is_file():
            continue
        rel = path.relative_to(skill_dir)
        if any(part in CACHE_DIRS or part in PACKAGING_DIRS for part in rel.parts):
            continue
        target_rel = f"{prefix}/{skill_dir.name}/{rel.as_posix()}"
        files[target_rel] = path.read_bytes()
        if path.stat().st_mode & stat.S_IXUSR:
            executable.add(target_rel)
    return files, executable


def collect_workflows(source_root: Path, layout: str, prefix: str) -> dict[str, bytes]:
    if layout not in render.LAYOUTS:
        raise ValueError(f"unknown layout: {layout}")
    workflows_root = source_root / ".agents" / "workflows"
    if not workflows_root.is_dir():
        return {}
    allowed = render.LAYOUTS[layout]["workflows"]
    names = list(allowed) if allowed is not None else []
    files: dict[str, bytes] = {}
    readme = workflows_root / "README.md"
    if readme.is_file():
        files[f"{prefix}/README.md"] = readme.read_bytes()
    for name in names:
        wf = workflows_root / f"{name}.md"
        if wf.is_file():
            files[f"{prefix}/{wf.name}"] = wf.read_bytes()
    return files


def host_prefix(host: str) -> str:
    return ".github" if host == "copilot" else f".{host}"


def build_host_plan(
    host: str,
    source_root: Path,
    layout: str = "full",
) -> SyncPlan:
    if host not in render.HOSTS:
        raise ValueError(f"unsupported host: {host}")
    safe_path(source_root, ".agents/agents")
    for role in (source_root / ".agents/agents").glob("*.md"):
        if role.is_symlink():
            raise ValueError(f"refusing symlink source: {role}")
    roles = render.load_roles(source_root, layout)
    rendered = render.render(host, roles, layout)

    base = host_prefix(host)

    def qualify(subpath: str) -> str:
        return f"{base}/{subpath}"

    files: dict[str, bytes] = {}
    executable: set[str] = set()

    for rel_path, content in rendered.items():
        if rel_path in {"STARTUP.md", "AGENTS.md"}:
            continue
        host_dot = f".{host}/" if host != "copilot" else ".github/"
        stripped = rel_path[len(host_dot) :] if rel_path.startswith(host_dot) else rel_path
        files[qualify(stripped)] = content.encode("utf-8")

    sources: dict[str, Path] = {}
    for skill_dir in iter_skill_dirs(source_root, layout):
        optional = skill_dir.parent.name == "optional"
        prefixes = []
        if host in {"claude", "cursor", "pi"}:
            prefixes.append(f"{base}/skills")
        # Codex and Gemini share this discovery surface. Track its owners separately.
        if optional:
            prefixes.append(".agents/skills")
        for prefix in prefixes:
            copied, modes = collect_skill_tree(skill_dir, prefix)
            files.update(copied)
            executable.update(modes)
            for rel in copied:
                sources[rel] = skill_dir / Path(rel).relative_to(f"{prefix}/{skill_dir.name}")

    workflows = collect_workflows(source_root, layout, qualify("workflows")) if layout == "full" else {}
    files.update(workflows)
    for rel in workflows:
        sources[rel] = source_root / ".agents/workflows" / Path(rel).name
    files[qualify("STARTUP.md")] = render.startup_contract(layout).encode("utf-8")
    for rel, source in sources.items():
        if not rel.endswith(".md"):
            continue
        def rebase(match):
            target = match.group(2)
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or target.startswith(("#", "/", ".agents/")):
                return match.group(0)
            linked = (source.parent / parsed.path).resolve()
            # Link only within the same discovery surface: shared .agents/skills copies must
            # render identically for every host, so they never point into one host's folder.
            candidates = [dest for dest, original in sources.items()
                          if original.resolve() == linked
                          and dest.startswith(f"{base}/") == rel.startswith(f"{base}/")]
            if candidates:
                rebased = posixpath.relpath(candidates[0], posixpath.dirname(rel))
                rebased += ("?" + parsed.query if parsed.query else "")
                rebased += ("#" + parsed.fragment if parsed.fragment else "")
                return f"{match.group(1)}{rebased}{match.group(3)}"
            if not linked.exists():
                return match.group(0)
            try:
                canonical = linked.relative_to(source_root.resolve()).as_posix()
            except ValueError:
                return match.group(0)
            canonical += ("?" + parsed.query if parsed.query else "")
            canonical += ("#" + parsed.fragment if parsed.fragment else "")
            return f"{match.group(1)}{canonical}{match.group(3)}"
        files[rel] = MARKDOWN_LINK.sub(rebase, files[rel].decode()).encode()
    return SyncPlan(files=files, executable=executable)


def build_plan(
    hosts: list[str],
    source_root: Path,
    layout: str = "full",
) -> SyncPlan:
    files: dict[str, bytes] = {}
    executable: set[str] = set()
    for host in hosts:
        plan = build_host_plan(host, source_root, layout=layout)
        files.update(plan.files)
        executable.update(plan.executable)

    return SyncPlan(files=files, executable=executable)


def safe_path(root: Path, relative: str) -> Path:
    """Resolve a repository-relative path, refusing traversal and symlink components."""
    if root.resolve() in {Path.home().resolve(), Path("/")} :
        raise ValueError("global targets are not supported")
    rel = Path(relative)
    if rel.is_absolute() or not rel.parts or any(part in {"", ".", ".."} for part in rel.parts):
        raise ValueError(f"unsafe repository-relative path: {relative}")
    if root.is_symlink():
        raise ValueError(f"refusing symlink root: {root}")
    root = root.resolve()
    path = root
    for part in rel.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"refusing symlink path: {relative}")
    if not path.resolve().is_relative_to(root):
        raise ValueError(f"path escapes repository: {relative}")
    return path


def reject_file_ancestors(root: Path, relatives: set[str]) -> None:
    for relative in relatives:
        path = root
        for part in Path(relative).parts[:-1]:
            path = path / part
            if path.exists() and not path.is_dir():
                raise ValueError(
                    f"cannot sync {relative}: ancestor {path.relative_to(root)} is a file; "
                    "for linked worktrees, leave hooks unsynced and run "
                    "`git -c core.hooksPath=.agents/guardrails commit ...`"
                )


def manifest_path(target_root: Path, hosts: list[str]) -> Path:
    if len(hosts) == 1:
        return target_root / host_prefix(hosts[0]) / MANIFEST_NAME
    return target_root / MANIFEST_NAME


def read_manifest(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        managed = data.get("managed_files", [])
        if not isinstance(managed, list) or not all(isinstance(item, str) for item in managed):
            raise ValueError("invalid managed_files")
        return set(managed)
    except (OSError, ValueError, TypeError):
        return set()


def is_shared(relative: str) -> bool:
    return any(relative.startswith(f".agents/skills/{name}/") for name in OPTIONAL_NAMES)


def shared_state(root: Path) -> tuple[set[str], set[str]]:
    path = safe_path(root, SHARED_MANIFEST)
    entries = read_manifest(path)
    owners = set()
    if path.exists():
        data = json.loads(path.read_text())
        owners = set(data.get("hosts", []))
        if not owners <= set(render.HOSTS):
            raise ValueError("invalid shared skill owners")
    # Migrate shared copies owned by older root/per-host manifests, if present.
    for base in ("", *(host_prefix(host) for host in render.HOSTS)):
        old = safe_path(root, (Path(base) / MANIFEST_NAME).as_posix())
        legacy = {rel for rel in read_manifest(old) if is_shared(rel)}
        if legacy:
            data = json.loads(old.read_text())
            owners.update(data.get("hosts", [base.lstrip(".")]) if base else data.get("hosts", []))
            entries.update(legacy)
    for rel in entries:
        safe_path(root, rel)
        if not is_shared(rel):
            raise ValueError(f"unsafe shared skill ownership: {rel}")
    return entries, owners


def read_ownership(target_root: Path, hosts: list[str], plan: SyncPlan):
    """Transfer selected native paths; centralize ownership of shared optional skills."""
    prefixes = tuple(f"{host_prefix(host)}/" for host in hosts)
    managed, remaining = set(), {}
    for base in ("", *(host_prefix(host) for host in render.HOSTS)):
        path = safe_path(target_root, (Path(base) / MANIFEST_NAME).as_posix())
        entries = read_manifest(path)
        for rel in entries:
            safe_path(target_root, rel)
        selected = {rel for rel in entries if is_shared(rel) or
                    (rel.startswith(prefixes) and (not base or rel.startswith(f"{base}/")))}
        managed.update(rel for rel in selected if not is_shared(rel))
        remaining[path] = entries - selected
    shared, owners = shared_state(target_root)
    if any(is_shared(rel) for rel in plan.files) or not (owners - set(hosts)):
        managed.update(shared)
    return managed, remaining


def apply_plan(
    target_root: Path,
    plan: SyncPlan,
    hosts: list[str],
    layout: str,
) -> tuple[list[str], list[str]]:
    if target_root.resolve() in {Path.home().resolve(), Path("/")}:
        raise ValueError("global targets are not supported")
    shared_path = safe_path(target_root, SHARED_MANIFEST)
    old_shared, owners = shared_state(target_root)
    next_owners = (owners | set(hosts)) if layout == "full" else (owners - set(hosts))
    manifest_rel = manifest_path(target_root, hosts).relative_to(target_root).as_posix()
    reject_file_ancestors(target_root, set(plan.files) | {manifest_rel, SHARED_MANIFEST})
    m_path = safe_path(target_root, manifest_rel)
    previously_managed, remaining = read_ownership(target_root, hosts, plan)
    reject_file_ancestors(target_root, previously_managed)

    # Check for unmanaged collisions before mutating anything
    collisions: list[str] = []
    identical_unmanaged: set[str] = set()
    for rel, content in plan.files.items():
        dest = safe_path(target_root, rel)
        if dest.exists() and rel not in previously_managed:
            if dest.is_file() and dest.read_bytes() == content:
                identical_unmanaged.add(rel)
                continue
            collisions.append(rel)
    if collisions:
        joined = ", ".join(sorted(collisions)[:5])
        more = f" (+{len(collisions) - 5} more)" if len(collisions) > 5 else ""
        raise FileExistsError(
            f"refusing to overwrite existing unmanaged files: {joined}{more}"
        )

    written: list[str] = []
    for rel, content in sorted(plan.files.items()):
        if rel in identical_unmanaged:
            continue
        dest = safe_path(target_root, rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_dir():
            raise FileExistsError(f"refusing to replace directory: {rel}")
        dest.write_bytes(content)
        if rel in plan.executable:
            dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        written.append(rel)

    removed: list[str] = []
    stale = sorted(previously_managed - set(plan.files))
    for rel in stale:
        dest = safe_path(target_root, rel)
        if dest.is_file():
            dest.unlink()
            removed.append(rel)
            parent = dest.parent
            while parent != target_root and parent.exists():
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent

    m_path.parent.mkdir(parents=True, exist_ok=True)
    m_path.write_text(
        json.dumps(
            {
                "layout": layout,
                "hosts": hosts,
                "managed_files": sorted(remaining[m_path] | {rel for rel in set(plan.files) - identical_unmanaged if not is_shared(rel)}),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if layout == "full":
        shared_files = {rel for rel in plan.files if is_shared(rel)} - identical_unmanaged
    else:
        shared_files = old_shared if next_owners else set()
    if shared_path.exists() or shared_files or next_owners:
        shared_path.parent.mkdir(parents=True, exist_ok=True)
        shared_path.write_text(json.dumps({"hosts": sorted(next_owners),
                                         "managed_files": sorted(shared_files)}, indent=2) + "\n")
    # Retire transferred ownership so deleted files cannot be claimed again later.
    for path, entries in remaining.items():
        if path == m_path or read_manifest(path) == entries:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        data["managed_files"] = sorted(entries)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return written, removed


def check_plan(target_root: Path, plan: SyncPlan, hosts: list[str]) -> list[str]:
    previously_managed, _ = read_ownership(target_root, hosts, plan)
    problems: list[str] = []
    for rel, content in sorted(plan.files.items()):
        dest = safe_path(target_root, rel)
        if not dest.is_file() or dest.is_symlink():
            problems.append(f"missing: {rel}")
        elif dest.read_bytes() != content:
            problems.append(f"out of date: {rel}")
    for rel in sorted(previously_managed - set(plan.files)):
        dest = safe_path(target_root, rel)
        if dest.exists() or dest.is_symlink():
            problems.append(f"stale file from previous layout: {rel}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--layout",
        choices=tuple(render.LAYOUTS),
        default="simple",
        help="simple: core skills; full: optional procedures and native roles",
    )
    parser.add_argument(
        "--host",
        choices=(*render.HOSTS, "all"),
        default="all",
        help="CLI host to sync (claude, codex, gemini, copilot, cursor, pi, or all)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="write synced files to the target")
    mode.add_argument("--check", action="store_true", help="verify target files match the selected layout")
    args = parser.parse_args(argv)

    hosts = list(PRIMARY_HOSTS) if args.host == "all" else [args.host]
    target_root = ROOT

    try:
        plan = build_plan(
            hosts=hosts,
            source_root=ROOT,
            layout=args.layout,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    if args.check:
        problems = check_plan(target_root, plan, hosts)
        if problems:
            sys.stderr.write("\n".join(problems) + "\n")
            return 1
        print(f"OK: {len(plan.files)} files in sync for layout={args.layout} host={args.host} target={target_root}")
        return 0

    if args.write:
        try:
            written, removed = apply_plan(
                target_root=target_root,
                plan=plan,
                hosts=hosts,
                layout=args.layout,
            )
        except (FileExistsError, ValueError) as exc:
            parser.error(str(exc))
        print(
            f"Synced {len(written)} files (removed {len(removed)} stale) "
            f"for layout={args.layout} host={args.host} -> {target_root}"
        )
        return 0

    # Default dry-run summary
    print(f"Dry-run: layout={args.layout} host={args.host} target={target_root} ({len(plan.files)} files)")
    for rel in sorted(plan.files):
        print(f"  {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
