"""Validate the portable skill bundle without external dependencies."""

import re
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    skills = list((root / ".agents/skills").glob("*/SKILL.md"))
    if not skills:
        raise ValueError("No skills found")
    for path in skills:
        text = path.read_text()
        match = re.match(r"---\nname: ([a-z0-9-]+)\ndescription: ([^\n]+)\n---\n", text)
        if not match or match[1] != path.parent.name or len(match[2]) > 1024:
            raise ValueError(f"Invalid metadata: {path.relative_to(root)}")
        if not text[match.end() :].strip():
            raise ValueError(f"Empty skill: {path}")
    for path in root.rglob("*.md"):
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            if (
                "://" not in target
                and not target.startswith("#")
                and not (path.parent / target.split("#")[0]).exists()
            ):
                raise ValueError(f"Broken link in {path.relative_to(root)}: {target}")
    print(f"Validated {len(skills)} skills and all local Markdown links")


if __name__ == "__main__":
    main()
