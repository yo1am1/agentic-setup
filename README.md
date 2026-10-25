# Agentic setup

The environment I use with Claude Code, Codex and Gemini. I assembled the main
setup in a day, using skills and additions I had selected and merged over time.

By [Yehor Trepalin](https://github.com/yo1am1).

## Get started

Requires Python 3, Git and Make.

```sh
make ai full     # generate roles and skills for all three hosts
make ai-test     # run the environment tests
```

`make ai simple` keeps the three core skills and removes installer-owned optional
roles and skills. `make ai` shows the available modes without changing files.

## The setup

- Seven roles: coordinator, researcher, investigator, engineer, code reviewer,
  devil's advocate and simplifier.
- Core skills: Caveman, caveman-commit and project-flow.
- Optional tools: Council, Herdr, Cavecrew, Humanizer and Specs.md flows.
- Parallel work: separate assignments and worktrees, followed by review and
  integration. See the [team workflow](.agents/workflows/team.md).
- Safe installation: tracks generated files, preserves personal settings and
  refuses unknown-file collisions or unsafe paths.
- Git checks: optional hooks check isolated staged or outgoing snapshots.

Small changes stay solo. Full mode makes specialist roles available when useful.
The installer writes inside the repository; hooks require separate setup.

[Try a task](docs/demo.md) · [Agent instructions](.agents/README.md) ·
[Earlier library](library/README.md) · [Sources and licenses](PROVENANCE.md)

## Checks

```sh
uv sync --locked
make check
```

The 41 tests cover adapters, mode changes, file ownership, path safety, Git
snapshots and source integrity. They run locally without calling model providers.
