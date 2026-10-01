# Workflow: Debugging

1. Reproduce the failure or read the exact error/test output.
2. Identify the expected behavior from tests, API contracts, prompts, or existing patterns.
3. Locate the implementation responsible for that behavior.
4. Fix the implementation rather than weakening tests, unless the test is demonstrably wrong.
5. Make the smallest patch that addresses the root cause.
6. Re-run the focused failing command.
7. Run the broader relevant suite once the focused check passes.
8. Report root cause, changed files, validation output, and any residual risk.
