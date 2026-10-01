"""Validate the public instruction library without executing copied helpers."""
import ast
import hashlib
import json
from pathlib import Path

import yaml


def main():
    root = Path(__file__).resolve().parents[1]
    skills = list((root / ".agents/skills").glob("*/SKILL.md"))
    if not skills:
        raise ValueError("No skills found")
    for path in skills:
        text = path.read_text()
        if not text.startswith("---\n") or "\n---\n" not in text[4:]:
            raise ValueError(f"Invalid metadata: {path}")
        frontmatter, body = text[4:].split("\n---\n", 1)
        metadata = yaml.safe_load(frontmatter)
        if (not isinstance(metadata, dict)
            or metadata.get("name") != path.parent.name
            or not isinstance(metadata.get("description"), str)
            or not metadata["description"].strip()
            or not body.strip()):
            raise ValueError(f"Invalid metadata: {path}")
    manifest = json.loads((root / "source-manifest.json").read_text())
    seen = set()
    for item in manifest:
        if item["path"] in seen:
            raise ValueError(f"Duplicate manifest path: {item['path']}")
        seen.add(item["path"])
        path = root / item["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"Source export changed: {item['path']}")
        if not item["changes"] and item["source_sha256"] != item["sha256"]:
            raise ValueError(f"Unrecorded adaptation: {item['path']}")
        if path.suffix == ".py":
            ast.parse(path.read_text(), filename=str(path))
    print(f"Validated {len(skills)} skills; {len(manifest)} source exports; Python syntax")


if __name__ == "__main__":
    main()
