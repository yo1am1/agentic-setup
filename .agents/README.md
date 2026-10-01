# Shared agent layer

The canonical instruction library: full source-based rules, skills, workflows,
role prompts and Fusion templates. Derived from the `.agents` layer I use in
Gewgur, plus my installed personal skills. [Provenance](../PROVENANCE.md) records
original hashes and every public-configuration replacement.

- [rules](rules/) — 8 safety, Git, testing, agent, state, retrieval, prompt and observability guides.
- [workflows](workflows/) — code change, debugging, review, Jira lifecycle and research entry points.
- [skills](skills/) — task-specific capabilities, Caveman, Ponytail, autoresearch and Council/Fusion.
- [agents](agents/) — investigator, code reviewer and four specialist evaluation roles.
- [prompts/fusion](prompts/fusion/) — complete proposal, synthesis, planning and exact-plan voting templates.
- [profiles/langgraph-backend.md](profiles/langgraph-backend.md) — the full backend project guide, with public placeholders.

## Routing

Use [code-change](workflows/code-change.md) for ordinary implementation,
[debugging](workflows/debugging.md) for failures and [review](workflows/review.md)
for a diff audit. Load the matching skill rather than every skill. Use
[Fusion](workflows/fusion.md) for independent proposals and consensus; use
[autoresearch](skills/autoresearch/SKILL.md) when a fixed metric can rank trials.
Caveman controls communication; Ponytail controls implementation choices.
Target-project conventions take precedence over generic style preferences.

## Adapters

`.agents` is the canonical source. `AGENTS.md` selects which guides apply to a
project; plain rule/workflow Markdown is not automatically executed by every host.

```sh
make sync-agents
uv run python scripts/sync_agent_adapters.py --check
```

The source-based generator produces Claude rules, full skill directories and
role prompts, plus Cursor path-scoped rules. Generated copies are ignored in Git.
Edit canonical files and regenerate. No global hooks or provider settings are
installed. The instructions' external runtimes still need to exist in the host.
