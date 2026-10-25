# Adversarial Test Review

## Variables

### prompt

{{prompt}}

### previous_envelope

{{previous_envelope}}

### context_handoff_dir

{{context_handoff_dir}}

## Task

Challenge the green tests and specify behavioral faults they must catch. Write the
review to `<context_handoff_dir>/test_review.md`, then respond with ONLY valid
JSON matching `TestReviewOutput`:

```json
{
  "status": "success",
  "approved": false,
  "summary": "<test-strength verdict>",
  "findings": [
    {
      "requirement": "<behavior or adversarial case>",
      "met": false,
      "evidence": "<specific assertion, gap, or failure evidence>"
    }
  ],
  "blocking": ["<test weakness that must be fixed>"],
  "mutations": [],
  "artifacts": ["<context_handoff_dir>/test_review.md"],
  "notes_for_next_agent": "<precise additions required from test_writer>"
}
```

When approving, set approved=true, blocking=[], mark requirements met, and supply
1–5 mutations of this shape (use actual source and assertion text, not this example):

```json
{"path":"src/price.py","before":"return price * count","after":"return price + count","failure_marker":"AssertionError: wrong total","reason":"Checkout must multiply unit price by quantity"}
```
