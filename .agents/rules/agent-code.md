---
paths:
  - "src/agents/**"
  - "src/tools/**"
---

# Agent code rules

- Tools return state updates via `Command(update=...)`.
- Use `ToolRuntime` for state access, not `InjectedState`.
- Register tool metadata in `src/config/tool_registry.py` before implementing the tool.
- Preserve middleware order assumptions when changing agent wiring.
- Keep operational settings in config/constants modules, not inline literals.
