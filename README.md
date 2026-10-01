# Agentic setup

The rules, skills, workflows and prompts I use for AI-assisted development.
By [Yehor Trepalin](https://github.com/yo1am1).

The core comes from my Gewgur `.agents` layer: focused code changes, failure
analysis, review, validation, agent tool/state contracts, retrieval and LLM
observability. Full instructions and supporting scripts are retained.

| Area | Contents |
| --- | --- |
| [Rules](.agents/rules/) | Safety, Git, testing, agent code, prompts, retrieval, state and observability |
| [Workflows](.agents/workflows/) | Code change, debugging, review, Jira lifecycle, research setup/continuation and Fusion |
| [Skills](.agents/skills/) | All 13 Gewgur skills; autoresearch; Council/Fusion; Herdr; full Caveman and Ponytail skill sets |
| [Role prompts](.agents/agents/) | Investigator, code reviewer, bug hunter, senior Python, prompt engineer and devil's advocate |
| [Engineering prompts](.agents/prompts/) | Full planner, test writer, builder, adversarial reviewer, reviewer, documenter, scout and Fusion task/system templates |
| [Backend profile](.agents/profiles/langgraph-backend.md) | Full project guide for a FastAPI/LangGraph/retrieval backend |

## Use

Browse [.agents/README.md](.agents/README.md) for routing. Merge selected guides
into your project's agent layer and link the applicable rules/workflows from its
`AGENTS.md`. Project-specific skills keep their source `src/` paths and helper
imports; adapt those to the consuming repository. Jira defaults and a Drive folder
ID are placeholders, not working account configuration.

```sh
uv sync --locked
make check
make sync-agents
```

The adapter generator copies full skill directories, including referenced helper
scripts, into Claude's project skills; it also generates Claude rules/roles and
Cursor rules. Generated files stay out of the public source tree.

## Personal skills

- [Caveman](.agents/skills/caveman/SKILL.md): terse communication, plus commit, review, compression, help and stats instructions.
- [Ponytail](.agents/skills/ponytail/SKILL.md): minimal implementation, plus review, audit, debt, help and gain instructions.
- [Fusion](.agents/skills/fusion/SKILL.md) / [Council](.agents/skills/council/SKILL.md): the same complete anonymous research, fusion, voting and debate workflow under two invocation names.
- [Autoresearch](.agents/skills/autoresearch/SKILL.md): full create/run instructions and templates; runnable experiments are in [autoresearcher](https://github.com/yo1am1/autoresearcher).

## Host requirements

These are instruction files and selected helpers. Herdr/Council needs a Herdr
session and configured coding-agent CLIs. Caveman stats needs its original plugin
hooks; skills alone do not activate session hooks or auto-default modes. Compression
uses Claude or an Anthropic API key and can incur model costs. Ponytail gain figures
are upstream benchmarks, not measurements of my projects.

Google Drive helpers need the Google API/OAuth libraries and your own credentials.
LangSmith/PostHog helpers retain imports from the consuming backend; that backend
and its SDKs are not bundled. Jira requires your own MCP integration and mappings.
The project-development research entry points use the separately installed
`agent-env` CLI. No external integration is contacted by `make check`.

[Provenance](PROVENANCE.md) separates unchanged copies, configuration replacements
and the Fusion alias. [Third-party licenses](licenses/) retain Caveman/Ponytail
attribution. [Validation](VALIDATION.md) states exactly what the checks verify.
