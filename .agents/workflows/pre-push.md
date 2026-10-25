# Optional pre-push validation

Push requires explicit authorization. Inspect outgoing refs and run configured
checks against each outgoing tree; missing comparison history requires a full-tree
check. Deletions need separate review. No workflow or install command pushes.
See [guardrails](../guardrails/README.md) for optional uninstalled hooks.
