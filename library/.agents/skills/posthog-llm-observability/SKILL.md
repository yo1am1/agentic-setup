---
name: posthog-llm-observability
description: Use when adding, changing, or debugging PostHog LLM Observability instrumentation in this repo — $ai_generation/$ai_span events, distinct_id/session_id/trace resolution, or the analytics client singleton.
---

# PostHog LLM observability

## How events are captured

- `get_analytics_client()` (`src/lib/analytics.py`) is an `lru_cache` singleton:
  returns a real `PosthogClient` when `settings.posthog_api_key` is set, otherwise
  a no-op `NullAnalyticsClient`. Never instantiate a PostHog client directly —
  always go through this singleton.
- `PostHogCallbackHandler` (`src/lib/posthog_callback.py`) is a LangChain
  `BaseCallbackHandler` that manually captures `$ai_generation` (LLM/chat model
  calls) and `$ai_span` (chains, tools, graph nodes) events — LangChain's own
  auto-instrumentation is not used, so hierarchy/cost/token/latency fields are
  built by hand in this file.
- The handler is registered per request, not globally: see `src/core/invoke.py`
  and `src/core/stream.py` for the two call sites (non-streaming and streaming).

## Identity resolution (verified against the real handler, not assumed)

`_get_distinct_id(metadata)` tries, in order:
1. `metadata["posthog_distinct_id"]`
2. `metadata["distinct_id"]`
3. `metadata["user_id"]`
4. the `posthog_distinct_id` contextvar
5. the handler's constructor `distinct_id` argument
6. `_get_session_id(metadata)` as a last resort
7. the literal string `"system_fallback"`

`_get_session_id(metadata)` tries: `metadata["posthog_session_id"]` →
`metadata["session_id"]` → the `posthog_session_id` contextvar → the handler's
constructor `session_id` argument.

Metadata wins over everything, including an explicit constructor argument — set
identity via `metadata={"posthog_distinct_id": ..., "posthog_session_id": ...}`
on the LangChain/LangGraph call when you need it to take priority. Nothing in
this repo currently calls `.set()` on the two contextvars, so in practice they
are dead fallbacks — do not rely on them being populated.

## Trace linking

- Every AI Observability event must carry `$ai_trace_id`; events sharing a
  `$ai_trace_id` group into one trace in PostHog's UI. All `$ai_span`/
  `$ai_generation` capture sites in `posthog_callback.py` set it from the
  LangChain run's own trace id — do not invent a different id for a new event
  type.
- `src/lib/evaluation.py` (`PosthogEvaluationFeedbackBackend`) reuses this
  exact convention to inject LangSmith evaluation scores into an existing
  PostHog trace after the fact — confirmed live: `insert()` calls
  `capture(event="evaluation_feedback", properties={"$ai_trace_id": <LangSmith
  trace_id>, ...})`. See the `langsmith-trace-pull-audit` skill for the
  LangSmith side of that pipeline.

## Adding a new capture point

1. Get the client via `get_analytics_client()`, never construct one.
2. Call `.capture(event=..., distinct_id=..., properties={...})`; include
   `$ai_trace_id` if the event should appear in a trace timeline.
3. If the same logical event could be captured more than once, pass a
   deterministic `uuid` — PostHog dedupes on it. See
   `_evaluation_feedback_event_uuid` in `src/lib/evaluation.py` for the
   pattern (`uuid5` over stable identifying fields).
4. Test against `NullAnalyticsClient` or a stubbed `capture` — never send a
   real capture call to the shared PostHog project from a test or an ad-hoc
   script. To verify wiring safely, monkeypatch the underlying
   `posthog.Posthog` instance's `.capture` method (accessible as
   `get_analytics_client()._client`) rather than sending live events.

## Bundled script

`scripts/verify_capture.py` — stubs the transport-layer `.capture` before
anything runs, so it is safe against the real, shared PostHog project. Run
from repo root:

```bash
# what distinct_id/session_id would this metadata resolve to?
uv run python .agents/skills/posthog-llm-observability/scripts/verify_capture.py \
    --metadata '{"posthog_distinct_id": "abc"}'

# dry-run a new capture call and inspect the exact kwargs, without sending it
uv run python .agents/skills/posthog-llm-observability/scripts/verify_capture.py \
    --event my_new_event --properties '{"$ai_trace_id": "..."}' --distinct-id foo
```

Warns if `$ai_trace_id` is missing from `--properties`. Verified live against
the real handler and `get_analytics_client()`.

## Verification

```bash
uv run pytest tests/unit/lib/test_analytics.py tests/unit/lib/test_posthog_callback.py -v
```
