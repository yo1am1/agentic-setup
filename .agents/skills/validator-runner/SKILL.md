---
name: validator-runner
description: Use when selecting, running, and reporting validation commands such as pytest, ruff, make targets, adapter drift checks, and live suites.
---

# Validator Runner Skill

## Procedure

1. Select the smallest validation command that proves the current change.
2. Prefer focused tests first; run broader suites when risk or repo policy requires it.
3. Use `uv` and `make` targets from `AGENTS.md`; do not invent ad-hoc dependency commands.
4. Reject destructive or secret-touching shell commands.
5. Capture the command, exit code, and relevant stdout/stderr.
6. For functional/runtime changes, also inspect the emitted application logs to confirm the
   exercised code path, not just the exit code.
7. Report pass, fail, error, or timeout honestly.
8. Never claim validation passed without observed command output.

## Common commands

```bash
uv run pytest -m "not slow and not integration"
make format
make test
make lint
make scan
uv run python scripts/sync_agent_adapters.py --check
```

Prompt or grounding behavior changes also require the live suite requested in
`AGENTS.md` (`make test-grounding`) unless the user explicitly defers it.
