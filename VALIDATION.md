# Validation

## Main environment

`make check` verifies:

- YAML metadata for canonical main skills and the archived library.
- SHA-256 hashes for all recorded exports and Python syntax for exported scripts.
- Rejection of corrupted metadata and unrecorded source changes.
- The compatibility entry point routes to the main installer.
- 26 adapter tests and 12 installation/guardrail tests using the standard library.

The 38 environment tests cover all three primary host outputs, repeated installs,
simple/full transitions, shared ownership, generated links, preservation of user
files, collisions/symlinks, partial staging and outgoing Git refs. Tests create
temporary repositories and home directories. They install no live hooks or global
configuration. `make ai-test` runs only these environment tests.

`make ai full` plus an explicit `--layout full --check` validates generated files
in this checkout. Generated configuration does not prove that a real host launched
workers or that a provider-backed task succeeded. See [the demo](docs/demo.md) for
a separate live walkthrough.

The archived library's original validation record is kept in
[library/VALIDATION.md](library/VALIDATION.md). Unrelated applications and specs are
outside this environment check. No model, paid API, OAuth login or external
integration is exercised by these checks. Upstream licensing/runtime caveats remain
in the provenance.

## Recorded local check, 2026-10-25

`make check` passed: 40 tests (26 adapter, 12 installation/guardrail, two integrity
regressions). Metadata validation covers 38 canonical skills across the main
environment and preserved library; all 332 recorded exports pass their hashes.
The full layout was installed in this checkout and all 364 generated files passed
the explicit full-layout drift check. Seven role files exist for each primary host.
These are local packaging and safety checks, not a recorded live agent swarm.
