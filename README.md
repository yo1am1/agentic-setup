# Agentic setup

Portable guardrails, context rules, skills and sequential workflows distilled from
my coding-agent environment. By [Yehor Trepalin](https://github.com/yo1am1).

## Use

Inspect before copying. Merge selected .agents/ content into your project without
overwriting existing instructions. Link relevant rules and workflows from its
AGENTS.md; hosts differ in automatic discovery. Skills use SKILL.md frontmatter;
rules and workflows are ordinary Markdown. Nothing installs global hooks or changes
provider configuration.

| Skill | Purpose |
| --- | --- |
| [fusion](.agents/skills/fusion/SKILL.md) | Independent proposals, critique, synthesis and exact-plan voting |
| [research-start](.agents/skills/research-start/SKILL.md) | Fixed evaluation, baseline and bounded trials |
| [research-continue](.agents/skills/research-continue/SKILL.md) | Recover champion without erasing negative results |
| [sequential-agents](.agents/skills/sequential-agents/SKILL.md) | Plan, independent tests, implementation, checks and review |

Read [guardrails](.agents/rules/guardrails.md) and [context handoffs](.agents/rules/context.md).
[Autoresearcher](https://github.com/yo1am1/autoresearcher) provides runnable examples.

## Runtime boundaries

Instructions do not launch agents, enforce an OS sandbox or guarantee correctness.
They need a host supporting the requested tools. Herdr can manage persistent
coding-agent terminals; a workflow engine can enforce gates. Neither is required
to adapt this setup. My software factory is a separate implementation, not bundled here.

```sh
make check
```

Checks metadata and local links, not agent behavior. [Provenance](PROVENANCE.md)
records inspiration.
