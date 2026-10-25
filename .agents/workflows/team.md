# Team execution

Use when independent work saves more than coordination costs. Planning may be
brief, Specs.md, or Council; a team does not select a planning method.
Read [develop](develop.md) and the [role contract](../agents/README.md) first.

## Establish the host and task contracts

The main conversation is coordinator and integrator. Discover the active host and
respect an explicit user preference. Prefer Orca when available in the current
workspace. Use Herdr only when `HERDR_ENV=1` and a managed session is confirmed.
Load version-matched host guides before commands; role files alone do not register
agents or enforce read-only access. Select the host's actual mechanism through its
[adapter](../adapters/README.md):

- [Herdr](../optional/herdr/SKILL.md) requires a managed Herdr context and its installed skill. [Council](../optional/council/SKILL.md) uses
  that procedure until a different adapter has been verified.
- Orca uses Orca worktrees, terminals, handoffs, or supervised orchestration as
  requested. Read the relevant Orca skill; do not substitute native teammates.
- Claude teammates use Claude's native team lifecycle when actually available.
  Do not invent a shared API with Herdr or Orca.
- Focused native subagents use the current host's delegation tools. They do not
  imply a persistent team, Council, or isolated worktrees.

[Cavecrew](../optional/cavecrew/SKILL.md) can provide concise delegation conventions
when its actual role presets are available. Loading the skill does not register
those presets or grant delegation permission.

Start only when delegation is authorized by the user or applicable instructions.
Honor existing authorization without asking again. If required isolation or
permissions cannot be enforced, report that limit and serialize or retain solo
work within the authorized scope.

Each assignment names:

1. Owner, selected role, concrete question or behavior, acceptance criteria.
2. Relevant source context, inputs, and dependencies; no unnecessary secrets.
3. Explicit read/write scope, owned paths, isolated worktree, and base revision.
4. Actual tools and permission profile; required startup skills, including
   [Caveman](../skills/caveman/SKILL.md)
   unless the user selected another style. Preserve code and exact commands.
5. Expected result, validation, stop conditions, and blocker escalation.
6. Relevant prior authorization and the integration owner.

## Execute, integrate, clean up

1. Record the current branch, revision, and dirty/untracked state before creating
   worktrees. Preserve pre-existing changes. Transfer required untracked files
   with an explicit file list and reproducible copy or archive, then verify them
   in each destination. Avoid broad staging and inspect staged paths before any
   authorized commit.
2. Draw a short dependency list. Parallelize independent ready tasks; serialize
   consumers until inputs exist. Agree shared interfaces before edits.
3. Give every task its own branch and worktree, including read-only tasks. Name
   the supervisor's integration branch the **main task branch**; it may be a task
   branch such as `agents/runtime-adjustments`, not protected Git `main`. Assign
   each worker explicit paths and never share a writable checkout. Separate
   worktrees do not resolve conflicting edits to the same interface.
4. Workers report scope overlaps or blockers before affected edits. Coordinator
   resolves ownership; workers do not expand scope or transfer authorization.
   Researcher and reviewer assignments remain read-only through every tool.
5. Request concise handoffs: result, changed paths or revision, evidence, checks
   and observed outcomes, unresolved risks. [Humanizer](../optional/humanizer/SKILL.md) is available only for an
   explicitly assigned prose task, never code or structured tool arguments.
6. Integrator confirms dependencies are complete, inspects worker diffs,
   preserves user changes, and integrates serially. Use the host's supported handoff
   mechanism; obtaining a patch does not authorize a commit, push, publication, or external message.
7. Review the combined result and rerun affected checks after integration. Worker
   checks do not prove the combined result passes. Resolve integration defects
   before reporting completion.
8. End workers through the host lifecycle. Account for unmerged changes before
   removing task worktrees or branches; preserve user-owned and uncommitted work.
   Report retained work, pending checks, and any cleanup that needs authorization.
