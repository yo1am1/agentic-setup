---
name: specsmd
description: Use vendored SpecsMD flows for substantial requirements, design, tracked execution or ideation when that planning approach is selected.
---

# SpecsMD

Brief planning remains the default. When useful and selected, choose one flow:

- [Simple](wrappers/specsmd-agent.md): requirements, design and tasks.
- [FIRE](wrappers/specsmd-fire.md): intent and run tracking.
- [AI-DLC](wrappers/specsmd-master-agent.md): inception, construction and operations.
- [Ideation](wrappers/specsmd-ideation.md): Spark, Flame and Forge.

The twelve invocation guides are consolidated in [wrappers](wrappers/); load only
the chosen flow and relevant resources. They are procedure guides, not installed
slash commands. All `.agents/optional/specsmd/resources/` paths resolve from the
repository root. Preserve existing project configuration and user instructions.

Resources are vendored once under [resources](resources/). No installer or download
framework is included. JavaScript helpers require Node; AI-DLC also needs fs-extra
and js-yaml, declared in [upstream-package.json](upstream-package.json). Report missing
capabilities before execution; do not install packages or global tools automatically.
The upstream Operations rollback procedure is unavailable. Workflows do not authorize
delegation, deployment, commits or pushes. See [provenance](../PROVENANCE.md).
