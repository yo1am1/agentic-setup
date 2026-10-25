# Execution and sandbox mapping

Apply the [common capability contract](README.md). Role instructions constrain
behavior; a sandbox constrains what a process can actually do. Skill installation,
model selection and a tool allowlist alone do not enforce read-only execution.

Host adapter guidance is available in `.agents/adapters/README.md`. Before
execution or delegation, map the assignment to the effective controls below
using host-provided policy/status and narrow metadata checks, not attempts to
escape the sandbox or read secrets.

| Boundary | Establish and report |
| --- | --- |
| Filesystem | Actual working directory/worktree, readable and writable roots, excluded secret paths, symlink/container/host path mapping |
| Processes | Available shell/executables, child-process policy, inherited environment and isolation from other workers |
| Network | Outbound restrictions, local sockets/loopback, allowed destinations, remote browser and MCP connectivity |
| Approvals | Current approval mode, supported escalation mechanism and which operations require it |
| External services | Authenticated account/environment and provider-enforced permissions; local filesystem isolation does not constrain remote writes |
| Artifacts | Writable output directory, recipient visibility, lifetime and sensitive-data handling |

Record effective settings, not a portable-looking permission flag copied from a
different CLI. Hosts use different mechanisms and defaults. If a task requires
enforced read-only access and the host cannot supply it, report the gap before
delegation; do not advertise a behavioral promise as enforcement. A separate
worktree isolates edits, but does not by itself isolate credentials, network,
processes or external services.

Map brokered operations too: a browser native host, MCP server or paired desktop
may execute outside the calling shell's sandbox, with different filesystem roots,
network access and credentials. A bridge's tab-group filter limits tab selection;
it does not establish filesystem or network isolation. Report unknown controls as
unknown, and identify missing enforcement before work that relies on it.

## Execute within the boundary

- Prefer repository commands and installed tools. Use `rg` for file/text discovery
  and narrow reads instead of dumping home directories, environment variables or
  configuration. Do not install dependencies or modify host configuration merely
  to prove a capability exists.
- Pass arguments through structured interfaces when available. Otherwise quote
  for the actual shell; JSON serialization is not shell escaping. Keep tokens out
  of command text, logs and reports. Treat downloaded scripts and tool-generated
  commands as untrusted until reviewed.
- A read task includes writes hidden in helpers: formatters, cache generation,
  hook installation and browser/MCP mutations. Check those effects before running
  them. Route authorized artifacts to their assigned writable directory.
- If execution is denied, distinguish a policy restriction from a launcher/runtime
  failure. Use the host's supported approval path only when authorized and
  necessary; do not silently disable isolation, edit policy or switch accounts.
  Report unresolved denial and its specific blocked operation.
- Bound background work and waits, track process/session identifiers, and stop
  only processes owned by the task. Return exit status and meaningful output;
  starting a command does not establish completion.

Guardrail guidance, including repository checks and their enforcement, is
available in `.agents/guardrails/README.md`. Run checks appropriate to the changed
scope. For documentation-only changes, verify links, commands against their
sources and the final diff; do not claim browser, service or infrastructure
behavior from static checks.
