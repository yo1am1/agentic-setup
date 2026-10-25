# Agentic setup

The root `.agents/` directory is the main environment. `library/` preserves the
older instruction collection and its generator. Read `.agents/README.md`, core
Caveman/project-flow and the relevant rules before making changes.

- `make ai simple` / `make ai full`: install repository-local host guidance.
- `make ai-test`: run isolated adapter, installation and guardrail tests.
- `make check`: validate metadata, source hashes, Python syntax and all tests.

Preserve complete upstream instructions and license notices. When changing an
exported file, update its hash and adaptation record in `source-manifest.json`.
Keep generated adapters, credentials and live session state out of Git.
Do not execute copied workflows or contact integrations to validate the setup.

Read `.agents/skills/caveman-commit/SKILL.md` before staging or composing commits.
Preserve existing user changes. Commit, push and external actions require the
user's authorization.
