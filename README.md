# Agentic setup

My actual coding-agent skills and workflows, exported from the setup I use.
By [Yehor Trepalin](https://github.com/yo1am1).

| Skill | What it does | Runtime |
| --- | --- | --- |
| [autoresearch](.agents/skills/autoresearch/SKILL.md) | Create experiments; run or continue champion-based loops; retain failures; optional MLflow | Coding agent + uv + experiment dependencies |
| [council](.agents/skills/council/SKILL.md) | Independent anonymous research, lossless fusion, hash-acknowledged voting and debate | Herdr session, selected agent CLIs; caveman skill unless plain style is selected |
| [sssf](.agents/skills/sssf/SKILL.md) | Operate deterministic software-factory workflows, typed outputs, gates, retries and traces | Full SSSF engine checkout; pi; configured providers |
| [factory-commands](.agents/skills/factory-commands/SKILL.md) | Explain global/per-project just recipes, costs, writes and session chaining | Existing factory and its justfiles |

The instructions, references, templates and supporting scripts are preserved from
installed sources, not rewritten as shorter substitute skills. Older entry-point
workflows are preserved in [.agents/workflows](.agents/workflows).

## Use

Copy selected skill directories into your host's skill search path. Check its
instructions and required runtimes before invoking it. Codex discovers project
skills under `.agents/skills`; Claude Code can use selected directories under
`.claude/skills`. Do not overwrite existing skills blindly.

`autoresearch` is self-contained as an instruction/template bundle. `council`
requires Herdr and its CLI integrations, including the installed caveman skill for
the default style; choose `style=plain` if that skill is unavailable.

The SSSF export is a source snapshot for inspecting my setup, **not a standalone
factory installation**. Its installer expects the full engine's `adws/`, rosters,
prompts and justfile; this repository does not contain that engine. Its own
runtime requirements and permission boundaries remain documented in the skill.
The factory-commands skill also records older recipes; use your engine's current
justfile as the command authority.

## Verify the export

```sh
make check
```

This checks metadata, the copied-file SHA-256 manifest and Python syntax. It does
not launch agents or spend model tokens. [Provenance](PROVENANCE.md) records source
paths, exclusions and runtime limitations. [Autoresearcher](https://github.com/yo1am1/autoresearcher)
contains the research experiment.
