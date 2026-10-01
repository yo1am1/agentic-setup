---
paths:
  - "src/config/state.py"
  - "src/core/utils/state.py"
  - "src/graph.py"
---

# State and persistence

- Evolve state via typed fields and reducers; explicit merge/replace semantics.
- `final_response_payload` (`{header, body, footer, products}`) is always assembled by `supervisor_node` at turn end; the products agent may pre-populate it, but `supervisor_node` overwrites unconditionally.
- `hinted_product_id`: per-turn product hint from `body.extra.extra_context.product_id`; injected into supervisor and products agent prompts.
- `extra_context`: free-form dict forwarded from the API request body's `extra` field.
- `disclaimer_text`: medical disclaimer appended when medical classification triggers it.
- Message trimming is active in the model-call path; do not assume summarization is wired in.
- Use centralized state utilities (`src/core/utils/state.py`) for CRUD and persistence.
