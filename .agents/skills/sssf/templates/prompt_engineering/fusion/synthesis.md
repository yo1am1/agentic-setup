# Fusion Synthesis

## Variables

### prompt

{{prompt}}

### previous_envelope

{{previous_envelope}}

### context_handoff_dir

{{context_handoff_dir}}

## Task

Synthesize the proposals into one implementable Markdown plan. Include scope,
repository evidence, minimal changes, acceptance tests, risks and user decisions.

**You have no tools, and you need none.** Every proposal from both rounds is
already in `previous_envelope`, including the `file:line` evidence the panel
gathered. Your job is to turn that argument into one plan — carry their evidence
forward and cite it as they did. You are not a fourth investigator: re-deriving
the problem yourself is how this step becomes the most expensive one in the run
and how the debate you were given gets quietly discarded. If the panel's
evidence is too thin to decide something, say so in the plan as a user decision
or a risk; do not guess, and do not invent a `file:line` no proposal contained.

Explain significant tradeoffs and dissent; do not count votes as factual proof.
If previous_envelope contains a rejected plan and votes, revise to address the
specific objections. Do not implement, write files or claim user approval.

## Report

Respond with ONLY `FusionPlanOutput` JSON (the harness saves the plan):
Emit one raw JSON object and nothing else — no prose before or after, no markdown
fence. Escape every newline inside a string as \n; unescaped newlines are the most
common way this contract fails to parse. Keep string fields tight and factual.


```json
{"status":"success","summary":"<plan summary>","plan":"# Plan\n<complete Markdown plan>","artifacts":[],"notes_for_next_agent":"<remaining user decisions>"}
```
