---
name: sequential-agents
description: Coordinate planner, test writer, implementer and reviewer roles in explicit sequential stages when delegation is requested.
---

# sequential-agents

Read [../../workflows/development.md](../../workflows/development.md) and [../../rules/context.md](../../rules/context.md).
Use independent agents only when requested or permitted by host policy. Assign one
bounded stage and writable scope per role. Derive tests from requirements; reviewers
inspect the real diff and check output rather than self-reported claims.
Run checks between implementation and review; bound repair cycles and rerun checks
after every edit. Herdr may host persistent CLI sessions; it is optional, not a sandbox.
If delegation is unavailable, use one session and state that fact.
