# Workflow: Review

1. Inspect the current diff directly (`git diff` and, when relevant, `git diff --staged`).
2. Check correctness, security, state updates, validation coverage, and repo conventions.
3. Flag only issues that affect correctness, security, maintainability, or stated requirements.
4. For each finding, cite the file and line and propose the smallest safe fix.
5. Separate blockers from optional follow-ups.
6. Confirm which validation commands were run and whether their output was observed.
