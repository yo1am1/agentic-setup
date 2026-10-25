# Optional pre-commit validation

Confirm the action is authorized; preserve unrelated staged and unstaged edits.
Inspect explicit staged paths and record `git write-tree`. Run configured checks
against the complete index snapshot, including partial staging and deletions.
Project checks are opt-in in [policy](../guardrails/policy.json); none are enabled
by default. Environment tests do not claim application quality.

Fix only authorized failures, review restaging, and confirm the checked tree still
matches the index before an authorized commit. Failed configured checks block the
action. Hooks are optional and uninstalled; see [guardrails](../guardrails/README.md).
