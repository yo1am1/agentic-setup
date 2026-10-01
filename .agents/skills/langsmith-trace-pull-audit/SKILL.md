---
name: langsmith-trace-pull-audit
description: Use when pulling LangSmith runs/feedback for this repo, auditing evaluation coverage, or investigating a specific run, trace, or session in LangSmith.
---

# LangSmith trace pulling and auditing

## Pulling runs and feedback

- Use `langsmith.AsyncClient`, not the sync `Client` — matches the repo's async FastAPI/LangGraph stack.
- List runs: `client.list_runs(...)` is deprecated (removed after Jan 31, 2027; see
  https://docs.langchain.com/langsmith/smithdb-sdk-migration-query-runs#runs-query). Use
  `client.runs.query_v2(...)` instead. It takes `project_ids` (a list of project UUID
  strings, not names) rather than `project_name`, and `min_start_time`/`max_start_time`
  rather than `start_time`; `is_root` is unchanged. Resolve the project name to an id
  first with `await client.read_project(project_name=...)` (returns an object with `.id`).
  `query_v2` returns an `AsyncPaginator` that is directly async-iterable
  (`async for run in client.runs.query_v2(...)`). It has no total-item `limit` kwarg
  (only a per-page `page_size`) — cap a fetch by breaking out of the loop after N items.
  `is_root=True` scopes to top-level graph invocations, not every internal step.
- List feedback for a run: `client.list_feedback(run_ids=[str(run.id)], feedback_key=[...])`.
  Feedback keys default to `settings.evaluator_keys` (`src/config/settings.py`); pass
  explicit keys to scope a pull to specific evaluators. `list_feedback` is not deprecated —
  do not migrate it.
- Feedback carries `run_id`, `trace_id`, `session_id`, `key`, `score`, `comment`,
  `created_at` (unaware datetime — LangSmith's own convention; do not force-localize it).
  For a root run, `trace_id` observably equals `run_id` (verified against the live
  `playground` project) — do not assume this holds for non-root runs.
- The repo's reference implementation is `EvaluationAdapter.load_feedbacks` in
  `src/lib/evaluation.py` — reuse it for one-off pulls instead of hand-rolling a
  new client. The `read_project` + `runs.query_v2(is_root=True, ...)` shape was verified
  against the installed `langsmith` SDK's source and live type signatures (`read_project`
  returns an object with `.id`; `query_v2` returns an async-iterable `AsyncPaginator`) —
  confirm against a real project before relying on it for a new audit.

## Auditing

1. Scope the audit window explicitly with `start_time` — do not scan the whole
   project by default; LangSmith projects can hold months of runs.
2. To find missing/low evaluation coverage: list root runs for the window, then
   check which run_ids have zero feedback rows for the expected keys.
3. To find regressions: compare `score` distributions for the same `key`
   across two time windows rather than eyeballing individual runs.
4. To cross-check a run against the correlated PostHog trace, use its
   `trace_id` — see the `posthog-llm-observability` skill for how that trace
   was captured, and `src/lib/evaluation.py` for how the two are stitched
   together (`$ai_trace_id` = LangSmith `trace_id`).
5. Feedback flows one direction in this repo — LangSmith → PostHog/Mongo
   (`PosthogEvaluationFeedbackBackend`, `EvaluationDBBackend`). Never write an
   audit's findings back into LangSmith.

## Bundled script

`scripts/pull_feedback.py` — read-only (`runs.query_v2`/`list_feedback` only), safe
against the real project. Run from repo root:

```bash
# dump feedback records as newline-delimited JSON
uv run python .agents/skills/langsmith-trace-pull-audit/scripts/pull_feedback.py \
    --days 7 --limit 20 --keys tool_calling_correctness,product_relevance

# audit: report root runs missing any expected feedback key
uv run python .agents/skills/langsmith-trace-pull-audit/scripts/pull_feedback.py \
    --days 7 --limit 20 --audit
```

`--limit` bounds the number of root runs (not raw feedback rows) in both modes.
Verified live against `settings.langsmith_project`.

## Verification

```bash
uv run pytest tests/unit/lib/test_evaluation.py -v
```
