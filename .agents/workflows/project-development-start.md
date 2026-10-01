# Autoresearch for project development

This is the global development loop. It complements, and does not replace,
`autoresearch-start.md`.

## Contract before edits

Use this contract only when explicitly requested, or when a large, high-risk,
or drastic change has a useful primary metric that can compare candidates. Do
not use it for ordinary fixes, focused refactors, tests, docs, mechanical
changes, or routine configuration work.

For qualifying work:

1. Select or create `experiments/dev_<repo>_<task>/`.
2. Declare exactly one task-specific primary metric and its direction.
3. Fix the evaluation evidence and acceptance threshold.
4. Declare hard gates for correctness, security, compatibility, and protected
   user data. A gate failure cannot be traded for metric gain.
5. Track tokens, latency, cost, output bytes, and complexity as secondaries
   where measurable.
6. Record the user's approval boundary. Scaffolding and read-only baselines are
   allowed; costly, destructive, paid, or externally visible runs require the
   corresponding approval.

Use `agent-env autoresearch declare ...` so hooks can audit the governed turn.
Pass the hook-provided `--session-id` and `--turn-id` to every declaration,
exemption, and audit when agents run concurrently.

When this threshold is not met, implement directly and run proportionate tests.
Do not create an exemption merely because files changed.

## Trial loop

1. Inspect the repository state and preserve user changes.
2. Retrieve candidate code with `agent-env search`; inspect the source directly
   before editing.
3. Measure the baseline with the evaluator in `program.md`.
4. Create an isolated worktree when the repository is clean. If bootstrap state
   is already dirty, use a copied trial plus a reviewable patch and record that
   exception.
5. Make one generalized change motivated by one hypothesis.
6. Run focused checks, the evaluator, then proportionate regression checks.
7. Append a result: `keep`, `discard`, or `crash`. Preserve failures and
   negative results.
8. Promote only an approved candidate that improves the primary metric and
   passes every hard gate. Never auto-commit or auto-push.

## Stop and report

Stop on acceptance, exhausted ideas, three consecutive non-improvements, or a
plateau below 0.5% across the last three keeps. Report the champion, baseline
delta, hard-gate status, secondary costs, discarded hypotheses, and unrun work.

Existing experiments retain their historical schemas and statuses. Audit drift;
do not rewrite history.
