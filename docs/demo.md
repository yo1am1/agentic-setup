# Try the setup

In a fresh clone:

```sh
make ai full
python3 .agents/adapters/sync.py --host all --layout full --check
make ai-test
```

This generates seven roles for each host. Open a new session in your coding agent
and try a scoped task:

> Review how the installer handles edited generated files when switching from
> full to simple. Use an investigator and a reviewer in separate temporary
> worktrees if this host supports them. Reproduce any defect with a test, propose
> the smallest fix, and review the final diff. Do not commit or push.

The [team workflow](../.agents/workflows/team.md) covers assignments and handoffs.
Use the host's actual delegation tools; generating role files does not start agents.

To switch back to the smaller setup:

```sh
make ai simple
```
