# LangGraph backend project profile

Multi-agent product recommendation/chat backend: FastAPI + LangGraph (supervisor pattern),
Pinecone hybrid retrieval, MongoDB persistence. Python version is pinned in `pyproject.toml`.

## Setup & commands

Use `uv` for all Python execution and dependency work. Never edit `pyproject.toml` deps by
hand — use `uv add`.

```bash
make install          # install dependencies
make install-dev      # install with dev group
make run              # run API locally (uvicorn)
make test             # fast unit + translation suites (CI-aligned)
make format           # ruff format + fix
make lint             # ruff checks
make scan             # bandit + pip-audit
```

Fast test feedback: `uv run pytest -m "not slow and not integration"`.
Single test: `uv run pytest tests/unit/... -k <name>`.

## Shared agent layer

One-time per-machine setup (installs the pre-push gate, syncs adapters, builds the graph):

```bash
make setup-agents     # wraps scripts/setup-agent-env.sh
```

- `AGENTS.md` is the canonical always-on guide for every agent CLI.
- Tool-neutral rules, reusable skills, workflows, and role prompts live in `.agents/`.
- `.agents/` is read natively by Codex (`.agents/skills` + `AGENTS.md`) and Copilot/VS Code
  (`.agents/skills` + `AGENTS.md`) — those tools need no generated adapter folder.
- Adapters are generated only for tools that cannot read `.agents/` directly:
  `.claude/{rules,skills,agents}` (Claude Code) and `.cursor/rules/*.mdc` (Cursor). Do not
  edit those generated copies directly.
- After changing `.agents/`, run `make sync-agents` (or
  `uv run python scripts/sync_agent_adapters.py --write`).
- Before committing agent-environment changes, run
  `uv run python scripts/sync_agent_adapters.py --check`.

## Architecture map

- Graph entry/flow: `src/graph.py` (init → assemble_context → supervisor → memory_save → END)
- Supervisor: `src/agents/supervisor.py` — the top-level decision point
- Capabilities as tools: products (`src/agents/products_agent.py`), medical, service, user settings
- State schema: `src/config/state.py`; tool metadata: `src/config/tool_registry.py`
- Retrieval: `src/pinecone_helpers/` (v2 strategy modules); tuning values in `src/config/constants.py`
- Prompts: `src/prompts/` (versioned in repo, formatted at runtime)
- Errors: `src/errors/` (typed exceptions + internal error codes)
- Agent behavior guidance: `src/skills/{agent_name}/*.md`

## Design principles

- KISS first: simple explicit control flow over clever abstraction. When in doubt, pick the
  implementation that is easier to test, debug, and maintain.
- Reuse the established patterns (`create_agent`, middleware composition, `ToolRegistry`,
  `Command(update=...)`) before introducing a new one.
- Open/Closed: extend through new tools, middleware, or strategies — do not modify unrelated
  stable code.
- Single Responsibility: one capability per module/tool; small focused interfaces over
  catch-all structures.
- DRY only when duplication is real and recurring; a single source of truth for config and
  metadata (constants, tool registry). If deduplication hurts readability, keep the
  duplication.
- No speculative or generalized architecture without a clear current need.

## Code style

- No global variables; use the existing singleton patterns (e.g. `get_instance()`).
- No nested function definitions — helpers live at module level.
- Tools return state updates via `Command(update=...)`; state access via `ToolRuntime`.
- Register tool metadata in `src/config/tool_registry.py` before implementing a tool.
- Operational settings live in config/constants modules, never inline literals.
- Retry logic uses the tenacity `@retry` decorator.
- Prefer simple explicit code over defensive patterns and speculative abstraction.
- Agent skill `.md` files: principle-based rules only, no illustrative examples.

## Testing

- Markers: `slow` (LLM calls), `integration` (external services), `langsmith`.
- `make test` must pass before push (enforced by the pre-push git hook). Skipped only when
  every commit being pushed is chore/docs/style/ci/build (non-functional); `make scan` always
  runs regardless.
- Never claim tests passed without showing command output.
- For functional/runtime changes, green tests are not enough on their own: also inspect the
  emitted application logs (structured `extra={"extra": {...}}` fields from `src/lib/logging`)
  to confirm the code path actually exercised is the one intended.
- Prompt/grounding changes: also run `make test-grounding` (live LLM, sequential, costs money).
- e2e routing suite is LLM-based: ~94% is the noise floor; compare to a baseline run.

## Security

- Never edit `.env`, secrets, keys, or credentials.
- Never run destructive commands (`rm -rf`, `git reset --hard`, force-push) without approval.
- New env vars in `src/config/settings.py` must also be added to
  `.octopus/tfvars/common.tfvars.json` if that file exists.

## Git workflow

- Main branch: `master`.
- Branch naming convention (strictly matching Jira Cloud / Bitbucket Branching Model):
  - **Feature**: `feature/PROJECT-<ticket>-<short-description>`
  - **Bugfix**: `bugfix/PROJECT-<ticket>-<short-description>`
  - **Hotfix**: `hotfix/PROJECT-<ticket>-<short-description>`
  - **Other / Task / Chore**: `PROJECT-<ticket>-<short-description>` (direct key slug without custom prefix)
  - *Warning*: Never use prefixes like `chore/`, `docs/`, `refactor/`, or `ci/` in branch names — Jira's Development panel only recognizes `feature/`, `bugfix/`, `hotfix/`, and direct `PROJECT-<ticket>-...` (`Other`).
- Conventional Commits, subject line only, <= 72 chars: `type(scope): subject`
  (types: feat fix chore refactor docs test perf ci build style — enforced by commit-msg hook).
- No commit body and no trailers. Never add a `Claude-Session:` / tool-attribution trailer.
- Pre-push gate: `make format` and `make scan` always run; `make test` runs unless every
  pushed commit is chore/docs/style/ci/build (enforced by pre-push hook).
- Ask before committing; never push over a failing gate.
- PR lifecycle: When a PR is merged into `master`, the remote source branch is deleted, and Jira's Development panel displays the final `1 pull request MERGED` status.
