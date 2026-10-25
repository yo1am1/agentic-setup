# Repo-local adapters

`python3 sync.py` uses only the standard library and writes only this repository.
`make ai simple` installs core skills without native roles; `make ai full` adds
seven roles and optional procedures. Both target Claude, Codex and Gemini together.
Core includes Caveman, caveman-commit and project-flow. Both startup contracts
require caveman-commit before staging or composing commits.
Installation does not run app checks, install dependencies, activate hooks or call
providers. No target/global option exists; unsafe paths and symlinks fail.

| Host | Roles (full only) | Skill discovery |
| --- | --- | --- |
| claude | `.claude/agents/*.md` | `.claude/skills/` |
| codex | `.codex/agents/*.toml` | `.agents/skills/` |
| gemini | `.gemini/agents/*.md` | `.agents/skills/` |
| copilot | optional renderer drafts | Native CLI not validated |
| cursor / pi | optional renderer drafts | Native CLI not validated |
| dsh / kimi | Unsupported | No verified renderer |
| Herdr / Orca | Host capabilities only | Read installed host guides |

Native registration/provider behavior is not tested by generating files.
Council stays Herdr-only. Rendering drafts never changes native host directories.

```sh
python3 .agents/adapters/sync.py --host codex --layout simple --write
python3 .agents/adapters/sync.py --host codex --layout simple --check
```

Owned generated paths are tracked in per-host/root manifests. Shared optional
copies in `.agents/skills/` use `.agents/.optional-sync-manifest.json`: a simple
host switch preserves copies still requested by another full host. Switching all
three with `make ai simple` removes owned optional copies and native roles.
Old ownership manifests migrate without claiming unmanaged files. Identical
unmanaged files remain unowned; different collisions fail before any mutation.
Unmanaged settings are never owned. Generated outputs are ignored, canonical
optional sources and native settings remain visible.
