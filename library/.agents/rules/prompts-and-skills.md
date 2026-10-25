---
paths:
  - "src/prompts/**"
  - "src/skills/**"
  - "src/translation/**"
---

# Prompt, agent-skill, and language rules

- Agent skill `.md` files contain principle-based rules only — no step-by-step examples.
- Ground catalog facts; never invent hypothetical causes for catalog discrepancies.
- Keep prompts versioned in the repository; format runtime context dynamically.
- Mandatory LangSmith Hub Synchronization: whenever modifying ANY prompt text or seed constant in `src/prompts/`, always synchronize the prompt to LangSmith Hub across environments (`dev`, `stage`, `preprod`, `prod`) via `uv run python scripts/migrate_prompts_to_langsmith.py --prompt <key> --env <env>` or manager `push_to_langsmith()`. Code constants (`*_SEED`) are strictly local fallbacks; running services pull active prompts directly from LangSmith Hub.
- After changing supervisor/agent prompts or grounding behavior, run `make test-grounding`.
- Language handling and translation live under `src/translation/`; behavior is environment-driven. Prompts are formatted dynamically at runtime (locale/personality).
