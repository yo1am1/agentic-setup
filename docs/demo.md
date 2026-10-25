# Demonstrate the setup

Use a fresh clone or a disposable copy. The local demonstration needs Python 3,
Git and Make; provider-backed execution also needs the selected coding-agent host.

## 1. Show the environment

```sh
make ai
make ai full
python3 .agents/adapters/sync.py --host all --layout full --check
```

Inspect `.claude/agents/`, `.codex/agents/` and `.gemini/agents/`. The seven roles
come from the same `.agents/agents/` definitions. Optional resources become
available through the host-specific discovery paths.

## 2. Show what is verified

```sh
make ai-test
```

These are 38 executable tests, not examples of expected output. They exercise
mode transitions, preservation of personal files, rejection of unsafe paths,
shared optional ownership and checks against isolated Git snapshots.

In a disposable clone, switch modes and check the new state:

```sh
make ai simple
python3 .agents/adapters/sync.py --host all --layout simple --check
make ai full
```

Only installer-owned optional files are removed. Unmanaged settings remain.

## 3. Run a live agent task

Open a new session in the configured host and give it a bounded task, for example:

> Review the installer's behavior when a user edits an owned generated role before
> switching from full to simple. Show the current contract and a reproducible test.
> Use an investigator and a reviewer if this host supports isolated workers. Give
> them separate temporary worktrees and read-only assignments. Integrate their
> findings, propose the smallest fix only if the contract is broken, and run the
> relevant offline checks. Do not commit, push, install hooks or contact providers
> beyond this session's model use.

Use the host's real delegation mechanism. The generated role files do not launch
workers on their own. Read the installed Orca/Herdr/native host guide before
using its commands; do not invent a common team API.

Show the actual work: assignment, independent findings, any necessary change,
test results and final diff. Record elapsed time from this run instead of using
an invented speed claim. If workers are unavailable, report that and run solo.

## 4. Explain the boundaries

The installer writes only inside the consuming repository. It installs no model
SDKs, hooks or global configuration. Optional Git checks require explicit setup;
application checks come from the project. Source integrity is recorded separately
from tests of model decisions or external services.

The previous instruction library can still be read under `library/`; it is not
mixed into the main root skill discovery path.
