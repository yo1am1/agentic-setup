---
name: add-tool
description: Add a new agent tool to this repo the house way. Use when creating or wiring a new tool for the supervisor, products, medical, or service capability.
---

# Add a tool

1. Define metadata in `src/config/tool_registry.py` first.
2. Implement the tool in `src/tools/`, decorated from the registry config.
3. Use `ToolRuntime` for state and tool-call context; typed inputs.
4. Return state updates via `Command(update=...)`.
5. Wire the tool into the owning agent (supervisor tool set or child agent).
6. Add tests: happy path and failure path, routing and state effects.
7. Run `uv run pytest -m "not slow and not integration"` and show the output.
