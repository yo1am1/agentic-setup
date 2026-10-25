# How I built this setup

I assembled the main environment in at most one day. Its ingredients were selected
and merged over time: skills I found useful, additions I tested, and procedures I
adapted to the way I work. The one-day figure describes assembly of the main setup;
it is not a claim that every bundled skill was written in a day or authored by me.

## The decisions I own

1. Keep one canonical environment and generate host-specific files from it.
   Claude, Codex and Gemini have different native formats; the role intent stays shared.
2. Make the small workflow useful on its own. Full mode adds specialist roles and
   optional procedures without making every change run a team or a planning framework.
3. Give parallel work an integration contract: bounded assignments, separate
   worktrees, explicit dependencies, reviewed transfers and checks after integration.
4. Track generated-file ownership. Switching modes should remove the setup's files,
   preserve personal configuration, and stop before overwriting an unknown file.
5. Verify those boundaries with temporary Git repositories. A clean install is
   only one case; repeat installation, mode changes, shared ownership, unsafe paths
   and partially staged work need checks too.

## What I can demonstrate

`make ai full` generates three host layouts and seven specialist roles. `make ai-test`
runs 38 offline tests. `make check` adds manifest, metadata, syntax and regression
checks. The [demo](demo.md) includes a concrete brief for a live agent walkthrough.
Actual agent execution depends on the installed host and its permissions.

The earlier backend instruction collection remains intact in `library/`. It is
useful reference material while the root environment is the current setup.

## Attribution and limits

The repository combines my integration work with attributed upstream skills and
resources. [PROVENANCE.md](../PROVENANCE.md) records sources and adaptations.
No throughput multiplier, customer-usage number, live swarm result or elapsed
implementation benchmark is claimed by the offline tests.
