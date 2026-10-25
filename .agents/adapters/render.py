#!/usr/bin/env python3
"""Render reviewable host role drafts inside .agents/adapters/generated."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
ADAPTERS = ROOT / ".agents" / "adapters"
LAYOUTS = {
    "simple": {"roles": (), "skills": ("caveman", "caveman-commit", "project-flow"), "workflows": ()},
    "full": {"roles": None, "skills": None,
             "workflows": ("develop", "team", "review", "pre-commit", "pre-push")},
}
STARTUP = """Full layout: core skills, seven native roles, and optional procedures available.
Brief planning and solo work remain default. Use teams, Council or SpecsMD only
when useful and authorized. Council stays Herdr-only; verify host availability.
Humanizer is prose-only and requires explicit selection.
Read `.agents/README.md` and `.agents/skills/project-flow/SKILL.md` for routing.
Read `.agents/skills/caveman-commit/SKILL.md` before staging or composing commits.
Roles and skills do not grant permission or install tools, hooks or dependencies.
"""
SIMPLE_STARTUP = """Simple layout: core Caveman, caveman-commit and project-flow skills; no native roles.
Use brief planning and solo execution by default. Optional procedures are not
installed. Read `.agents/README.md`; respect the user's scope and authorization.
Read `.agents/skills/caveman-commit/SKILL.md` before staging or composing commits.
"""


@dataclass(frozen=True)
class Role:
    name: str
    description: str
    body: str


def parse_role(path: Path) -> Role:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not match:
        raise ValueError(f"missing role frontmatter: {path}")
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip().strip("\"'")
    if not fields.get("name") or not fields.get("description"):
        raise ValueError(f"role needs name and description: {path}")
    return Role(fields["name"], fields["description"], match.group(2).strip())


def load_roles(source_root: Path, layout: str = "full") -> list[Role]:
    if layout not in LAYOUTS:
        raise ValueError(f"unknown layout: {layout}")
    files = sorted((source_root / ".agents" / "agents").glob("*.md"))
    if not files:
        raise ValueError(f"no role definitions under {source_root / '.agents/agents'}")
    roles = [parse_role(path) for path in files if path.name != "README.md"]
    allowed = LAYOUTS[layout]["roles"]
    if allowed is not None:
        allowed_set = set(allowed)
        roles = [role for role in roles if slug(role.name) in allowed_set]
    return roles


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def frontmatter(role: Role) -> str:
    return f"---\nname: {slug(role.name)}\ndescription: {role.description}\n---\n"


def role_body(host: str, role: Role) -> str:
    def rebase(match: re.Match[str]) -> str:
        target = match.group(2)
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or target.startswith(("#", "/")):
            return match.group(0)
        canonical = posixpath.normpath(posixpath.join(".agents/agents", parsed.path))
        return f"{match.group(1)}{canonical}{('?' + parsed.query) if parsed.query else ''}{('#' + parsed.fragment) if parsed.fragment else ''}{match.group(3)}"

    return re.sub(r"(!?\[[^\]]*\]\()([^)]+)(\))", rebase, role.body)


def startup_contract(layout: str = "full") -> str:
    if layout not in LAYOUTS:
        raise ValueError(f"unknown layout: {layout}")
    return SIMPLE_STARTUP if layout == "simple" else STARTUP


def render(host: str, roles: list[Role], layout: str = "full") -> dict[str, str]:
    contract = startup_contract(layout)
    output = {"STARTUP.md": contract}
    if host == "codex":
        output["AGENTS.md"] = contract
    for role in roles:
        name = slug(role.name)
        rendered_body = role_body(host, role)
        body = f"{frontmatter(role)}\n{rendered_body}\n\n## Shared startup contract\n\n{contract}"
        if host == "claude":
            output[f".claude/agents/{name}.md"] = body
        elif host == "codex":
            instructions = rendered_body + "\n\n" + contract
            output[f".codex/agents/{name}.toml"] = (
                f'name = {json.dumps(name)}\n'
                f'description = {json.dumps(role.description)}\n'
                f"developer_instructions = {json.dumps(instructions)}\n"
            )
        elif host == "gemini":
            output[f".gemini/agents/{name}.md"] = body
        elif host == "copilot":
            output[f".github/agents/{name}.agent.md"] = body
        elif host == "cursor":
            output[f".cursor/skills/{name}/SKILL.md"] = body
        elif host == "pi":
            output[f".pi/skills/{name}/SKILL.md"] = body
        else:
            raise ValueError(f"host has no verified renderer: {host}")
    return output


def write_files(destination: Path, files: dict[str, str]) -> None:
    targets = [(destination / relative, content) for relative, content in files.items()]
    existing = [path for path, _ in targets if path.exists()]
    if existing:
        raise FileExistsError(f"refusing to overwrite: {existing[0]}")
    for target, content in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


HOSTS = ("claude", "codex", "gemini", "copilot", "cursor", "pi")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", choices=(*HOSTS, "dsh", "kimi"))
    parser.add_argument("--layout", choices=tuple(LAYOUTS), default="simple")
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true", help="write drafts in generated/<host>")
    args = parser.parse_args(argv)
    if args.host not in HOSTS:
        parser.error(f"{args.host} has no verified renderer; see README.md compatibility matrix")
    try:
        files = render(args.host, load_roles(args.source_root, args.layout), args.layout)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    destination = (
        ADAPTERS / "generated" / args.host
        if args.layout == "full"
        else ADAPTERS / "generated" / args.layout / args.host
    )
    if args.write:
        try:
            write_files(destination, files)
        except FileExistsError as exc:
            parser.error(str(exc))
    for relative, content in files.items():
        target = destination / relative
        if args.write:
            print(f"wrote {target.relative_to(ROOT)}")
        else:
            print(f"--- {relative} ---")
            print(content, end="" if content.endswith("\n") else "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
