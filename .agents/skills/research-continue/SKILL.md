---
name: research-continue
description: Resume an interrupted experiment from its contract, configurations and results without resetting history.
---

# research-continue

Read [../../workflows/research.md](../../workflows/research.md) and [../../rules/guardrails.md](../../rules/guardrails.md).
Read contract, results, configurations and failure notes. Verify fixed data, evaluator,
model identity, lockfile and metric direction. Changed protocols start separate studies.
Recover the best accepted result; exclude crashes and failed correctness gates.
Confirm remaining authorization and budget. Choose one untried hypothesis and resume
sequentially. Preserve rejected candidates and treat ties as non-improvements.
Apply the original stopping/reporting contract; never silently reset the budget.
