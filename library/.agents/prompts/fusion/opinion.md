# Fusion Proposal / Debate

## Variables

### prompt

{{prompt}}

### previous_envelope

{{previous_envelope}}

### context_handoff_dir

{{context_handoff_dir}}

## Task

If no previous envelope exists, independently propose the best approach. Otherwise
critique all supplied previous-round proposals, identifying agreements, disagreements,
evidence and an improved proposal. Do not read other session files.

## Report

Respond with ONLY `FusionOpinionOutput` JSON:

```json
{"status":"success","summary":"<short position>","proposal":"<approach, file evidence, alternatives, acceptance tests>","risks":["<risk or unresolved user decision>"],"artifacts":[],"notes_for_next_agent":"<important disagreements>"}
```
