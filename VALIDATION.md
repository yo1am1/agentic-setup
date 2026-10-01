# Validation

Validated on 2026-10-01 with Python 3.12.3 and locked PyYAML 6.0.3.

`make check` passed:

- YAML metadata: all 29 complete skills.
- Manifest and Python syntax: 86 source exports; 77 unchanged copies; the other
  entries record configuration redactions, YAML quoting, the Fusion alias or the
  adapter extension.
- Two regression checks: metadata/source corruption rejected; helper resources
  copied into generated skill directories and drift rejected.
- Adapter generation and drift: all 78 generated files in sync.

The public tree has 8 rules, 9 workflows, 6 role prompts and 4 Fusion templates.
Factory/UI directories and live handover/session state are absent.

The checks run no agents, model calls, OAuth logins, Jira writes or live provider
operations. They establish packaging integrity, not the quality of model decisions
or compatibility with every agent host. Backend helpers retain their source
imports and need the consuming backend/SDKs. Plugin hooks, provider settings and
external runtimes are not installed by copying these instruction files.
