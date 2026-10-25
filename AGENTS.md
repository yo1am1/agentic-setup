# Agentic setup

The root `.agents/` directory is the main development-agent environment. Read
`.agents/README.md`, core Caveman/project-flow, and relevant rules. Default to
simple mode, brief planning and solo work; read the host STARTUP.md when installed.
User instructions and existing authorization control scope.

This repository distributes instructions and adapter code. Do not execute copied
workflows, call providers or operate external integrations to validate the library.
`library/` preserves the earlier environment and its full source instructions;
it does not define the root installer. Keep its instructions and attribution intact.

Use `make ai` to show modes, `make ai simple` for core skills, `make ai full` for
seven roles and optional procedures, and `make ai-test` for isolated environment
tests. Run `make check` for source hashes, metadata, syntax and all repository tests.
The installer/tests need the standard library; manifest validation uses the locked
PyYAML dependency. No global settings, hooks or application dependencies are installed.

Read `.agents/skills/caveman-commit/SKILL.md` before staging or composing commits.
Update CHANGELOG.md with user-facing changes for each commit. Commit, push,
external messages and deployment require authorization; skills grant none.
Preserve unrelated work in `apps/` and `specs/` unless explicitly assigned.

When changing an exported file, retain complete instructions, update its hash and
record the adaptation in source-manifest.json. Never add credentials, local host
settings, generated adapters or live session state. Native/provider compatibility
must be reported separately from generated-file and offline-test results.
