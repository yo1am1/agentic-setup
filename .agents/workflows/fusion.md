# Workflow: Fusion

Read the full [Fusion skill](../skills/fusion/SKILL.md). It is the complete
installed Council procedure exposed through a `/fusion` invocation; the original
[Council skill](../skills/council/SKILL.md) is retained too. They are two entry
points to the same process, not independent votes or extra research stages.

For Herdr research, follow that skill's configuration, independence, lossless
fusion, hash acknowledgement, voting, debate and reporting instructions.

The separate [Fusion prompt set](../prompts/fusion/) contains the original
`system.md`, `opinion.md`, `synthesis.md` and `vote.md` for structured plan review.
Render its `prompt`, `previous_envelope` and `context_handoff_dir` variables;
validate its named JSON output contracts in the calling host. These prompts
belong to a different structured-envelope execution path: do not replace the
Council ballot format with their JSON mid-run. Prompt files alone do not execute
or enforce the process.
