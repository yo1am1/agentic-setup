"""Validate source exports without running agents or changing source files."""
import ast
import hashlib
import json
import re
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    skills = list((root / ".agents/skills").glob("*/SKILL.md"))
    if not skills:
        raise ValueError("No skills found")
    for path in skills:
        text = path.read_text()
        parts = text.split("---", 2)
        if len(parts) != 3:
            raise ValueError(f"Invalid metadata: {path}")
        name = re.search(r"^name: ([a-z0-9-]+)$", parts[1], re.M)
        description = re.search(r"^description: (.+)$", parts[1], re.M)
        if not name or name[1] != path.parent.name or not description or not parts[2].strip():
            raise ValueError(f"Invalid metadata: {path}")
    manifest = json.loads((root / "source-manifest.json").read_text())
    for item in manifest:
        path = root / item["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"Source export changed: {item['path']}")
        if path.suffix == ".py":
            ast.parse(path.read_text(), filename=str(path))
    print(f"Validated {len(skills)} skills; {len(manifest)} exact source files; Python syntax")


if __name__ == "__main__":
    main()
