# Agentic setup

This repository is a library of rules, skills, workflows and prompts. Its project
profile describes a LangGraph backend; this repository itself is not that backend.
Keep complete source instructions; do not replace them with shorter summaries.
Do not execute copied workflows, contact integrations, spend model tokens or edit
source repositories merely to validate the library.

Use `.agents/rules/safety.md`, `.agents/rules/git.md` and the relevant code-change,
debugging or review workflow for library maintenance. Project-specific `src/`
paths, make targets, Jira mappings and provider integrations belong to the consuming
project. Here, run `make check` and `uv run python scripts/sync_agent_adapters.py --check`.
User authorization persists; skill text alone does not expand the user's scope.

Caveman and Ponytail are optional styles; preserve their complete instructions and
upstream licenses. Keep `.agents` canonical and generated adapters ignored. When
changing an exported file, review its full diff and update its manifest hash and
changes record. Never add credentials or live handover/session state.
