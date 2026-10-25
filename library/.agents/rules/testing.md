# Testing rules

- Fast feedback first: `uv run pytest -m "not slow and not integration"`.
- `make test` must pass before any push (enforced by the pre-push git hook). Skipped only
  when every commit being pushed is chore/docs/style/ci/build (non-functional); `make scan`
  always runs regardless.
- Never claim tests passed without showing the command output.
- For functional/runtime changes, green tests are not enough on their own: also inspect the
  emitted application logs (the structured `extra={"extra": {...}}` fields from
  `src/lib/logging`) to confirm the code path actually exercised is the one intended —
  especially for LangGraph/agent routing behavior that assertions alone don't fully pin down.

## Layout

- `tests/unit/core/` — agent flow tests + pure unit tests for core modules.
- `tests/unit/api/` — FastAPI endpoint tests.
- `tests/unit/lib|errors|skills|pinecone_helpers/` — unit tests per module.
- `tests/translation/` — language detection.
- `tests/agent/` — live LLM routing/quality suites (marked `slow`), incl. the grounding/honesty regression suite (`test_grounding_honesty_regression.py`, judge model set in `_llm_judge`).
- `tests/e2e/` — tool-call routing accuracy over parametrized scenarios.

## Live suites (cost money, nondeterministic, excluded from `make test`)

- `make test-grounding` — grounding/honesty suite; run sequentially (parallel trips rate limits).
- `make test-agent` — all live agent suites.
- `make test-e2e-routing` — routing accuracy, parallel (`WORKERS=N`).
- e2e routing is LLM-based: ~94% accuracy is the noise floor; compare against a baseline run, do not treat single flips as regressions.
- When changing supervisor/agent prompts or grounding behavior, also run `make test-grounding`.
