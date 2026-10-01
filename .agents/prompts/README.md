# Full engineering prompt library

These are the complete task/system prompt pairs from my personal agent setup,
with the separate Fusion proposal/synthesis/voting set. Instructions and JSON
examples are preserved rather than replaced with shorter role summaries.

| Role | Identity | Task/output contract |
| --- | --- | --- |
| Planner | [system](planner/system.md) | [user](planner/user.md) |
| Test writer | [system](test_writer/system.md) | [user](test_writer/user.md) |
| Builder | [system](builder/system.md) | [user](builder/user.md) |
| Adversarial test reviewer | [system](test_reviewer/system.md) | [user](test_reviewer/user.md) |
| Requirement reviewer | [system](reviewer/system.md) | [user](reviewer/user.md) |
| Documenter | [system](documenter/system.md) | [user](documenter/user.md) |
| Scout | [system](scout/system.md) | [user](scout/user.md) |
| Fusion panel | [system](fusion/system.md) | [proposal](fusion/opinion.md), [synthesis](fusion/synthesis.md), [vote](fusion/vote.md) |

Render `prompt`, `previous_envelope` and `context_handoff_dir` in the calling host.
The host must validate the declared output contract, authorize tools/writes and
run actual gates. Named schemas are documented through the complete JSON examples;
no workflow engine or schema implementation is bundled here.

The test-writer prompts retain their original quality-config path; the planner,
scout and documenter retain their session handoff layout. Map these to your host
before execution. Preserve the independent-test, read-only review, evidence and
exact-plan-hash boundaries when adapting. Copying prompts does not enforce those
boundaries by itself. Choose either the Council ballot protocol or the structured
Fusion JSON protocol; do not mix their formats during a run.
