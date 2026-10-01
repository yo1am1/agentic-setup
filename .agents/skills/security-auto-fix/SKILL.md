---
name: security-auto-fix
description: Use when `make scan` (bandit/pip-audit) fails and the vulnerability or finding needs to be fixed, pinned, or justified before the change can be pushed.
---

# Security Auto-Fix Skill

## Procedure

1. Run `make scan`; capture the full bandit and pip-audit output.
2. For a pip-audit finding with a fixed version available: bump via `uv add
   <package>>=<fixed_version>` — never hand-edit `pyproject.toml` dependency lines. Add the
   same inline `# Fix <ADVISORY_ID>` comment convention already used throughout the
   dependency list.
3. For a pip-audit finding with no fixed version yet: add `--ignore-vuln <ADVISORY_ID>` to
   the `scan` target in `Makefile` (its current, only location) with a comment stating why
   and what would resolve it. Never add an ignore silently or without a reason.
4. For a bandit finding: fix the flagged code. Only use `# nosec` with an inline justification
   for a genuine false positive; never blanket-suppress.
5. Re-run `make scan` after any fix and confirm it is clean before handing back.
6. Never claim `make scan` passed without showing the re-run output.
7. This skill fixes the code/config; it does not commit or push — a human still reviews and
   commits the result.
