# Workflow: Code Change

1. Restate the task and identify the intended behavior change.
2. Inspect the relevant implementation before editing.
3. Inspect related tests or examples.
4. Plan the smallest safe patch; avoid speculative architecture.
5. Apply the patch only to relevant files.
6. Run focused validation first.
7. Run broader validation required by `AGENTS.md` for the touched area.
8. Review the diff for minimality and unrelated changes.
9. Summarize changed files, reason for the change, commands run, results, and remaining risks.
