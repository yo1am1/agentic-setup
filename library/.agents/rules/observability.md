---
paths:
  - "src/lib/**"
  - "src/core/maintenance.py"
  - "src/core/middleware.py"
  - "src/handlers/maintenance.py"
---

# Observability, errors, maintenance

- Analytics: `get_analytics_client()` is an `lru_cache` singleton returning an `AnalyticsClient` (PostHog when `posthog_api_key` set, otherwise a no-op client). Initialized in lifespan.
- `PostHogCallbackHandler` captures `$ai_generation`/`$ai_span`; identity resolves from LangChain run metadata first, contextvars are currently dead fallbacks; registered per request in invoke/stream paths. See the `posthog-llm-observability` skill for the verified resolution order and how to add a capture point.
- LangSmith evaluation feedback is synced into PostHog by `src/lib/evaluation.py`, linked to the original trace via `$ai_trace_id`. See the `langsmith-trace-pull-audit` and `posthog-llm-observability` skills.
- Errors: raise typed exceptions from `src/errors/` with standardized internal codes; global API handlers shape responses.
- Structured logging: pass `extra={"extra": {"internalCode": ..., "httpStatus": ..., "criticality": ...}}`; `JsonFormatter` renders it.
- Maintenance mode: in-memory flag loaded from MongoDB `service_config` at startup; `MaintenanceMiddleware` blocks non-admin routes with HTTP 200 + `SERVICE_MAINTENANCE`; `/admin/` and `/health` excluded.
