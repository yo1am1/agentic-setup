# Sequential development

Inspect repository state and trace the behavior through its callers.
Plan the smallest change with verifiable acceptance criteria. For nontrivial
behavior, derive an independent regression check from the requirement.
Implement using established patterns, then run deterministic checks before review.
Give the reviewer the request, actual diff, check output and unresolved limitations.
Repair concrete failures within the budget; every edit invalidates prior checks.
Pass goal, evidence, artifacts and remaining budget between stages.
Commit, push and deploy only within explicit authorization.
