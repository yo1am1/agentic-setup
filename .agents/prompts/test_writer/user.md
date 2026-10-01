# Test Authoring Task

## Variables

### prompt

{{prompt}}

### previous_envelope

{{previous_envelope}}

### context_handoff_dir

{{context_handoff_dir}}

## Task

Write or strengthen tests for the behavior in `<context_handoff_dir>/plan.md`.
The first pass precedes implementation; later passes strengthen tests against
reviewed faults. Tests may already pass for existing correct behavior. Never
manufacture a red baseline: the harness will separately break production logic
in disposable copies and require assertion failures.

Respond with ONLY valid JSON matching `BuildOutput`:

```json
{
  "status": "success",
  "summary": "<what behavior the tests specify>",
  "changed_files": ["tests/test_feature.py", "adws/adw_sssf_config/quality.json"],
  "artifacts": [],
  "commit_message": "Add tests for <behavior>",
  "notes_for_next_agent": "<expected pre-implementation failure and why>"
}
```
