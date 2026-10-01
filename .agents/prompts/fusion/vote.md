# Fusion Plan Review

## Variables

### prompt

{{prompt}}

### previous_envelope

{{previous_envelope}}

### context_handoff_dir

{{context_handoff_dir}}

## Task

Review the exact complete plan in previous_envelope.summary against the request,
repository evidence, and earlier debate. Copy its supplied plan_sha256 exactly.
An acknowledgement of receipt is NOT approval: approve only if the plan is sound
and implementable with no blocking gap. User decisions may remain explicitly
identified, but an unresolved decision that changes the implementation is blocking.
Reject honestly; no consensus is preferable to concealing a defect. Never read
other participants' current votes. Do not write anything.

## Report

Respond with ONLY `FusionVoteOutput` JSON:

```json
{"status":"success","summary":"<verdict>","plan_sha256":"<supplied hash>","approved":false,"findings":[{"requirement":"<requirement>","met":false,"evidence":"<plan section or gap>"}],"blocking":["<concrete correction needed>"],"artifacts":[],"notes_for_next_agent":"<revision advice>"}
```

When approving, use approved=true, blocking=[], and mark all findings met.
