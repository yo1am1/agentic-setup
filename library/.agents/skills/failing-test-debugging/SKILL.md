---
name: failing-test-debugging
description: Use when a test fails and the agent must inspect test expectations, locate the implementation bug, make a minimal fix, and rerun the focused test.
---

# Failing Test Debugging Skill

## Procedure

1. Run or inspect the failing test.
2. Identify the expected behavior.
3. Inspect the implementation that should satisfy that behavior.
4. Prefer fixing implementation over weakening tests.
5. Make the smallest patch.
6. Run the focused test.
7. If it passes, run the relevant test suite.
8. Summarize the root cause and validation result.

## Common mistakes

- Do not rewrite unrelated files.
- Do not update tests to match wrong behavior.
- Do not claim tests passed without running them.
