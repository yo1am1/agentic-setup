# Development rules

- Follow user scope and repository safety rules; preserve existing edits.
- Brief planning and solo work are defaults in both modes. Simple loads core
  skills only; full makes optional procedures and native roles available.
- Use Caveman unless the user chooses another style. Humanizer is explicit-only
  prose editing. Never apply it to code, commands or structured tool arguments.
- Honor the user's host preference and use verified available capabilities.
  No automatic plugin, package or global configuration installation.
- Delegate only when useful and authorized. Give workers separate writable
  workspaces, bounded ownership and acceptance evidence; review integration.
- Stage explicit paths and honor existing action-specific authorization.
  Commit, push and external changes are separate actions.
- Read and apply [caveman-commit](../skills/caveman-commit/SKILL.md) before
  staging or composing commits. Use Conventional Commits with a concise imperative
  subject. Message-only requests return a message; authorized commit requests
  continue through the commit.
- Update root `CHANGELOG.md` in every commit. Read actual diffs and record
  the final user-facing result, grouping related changes and naming any
  required upgrade steps. Preserve released history and omit reversals,
  implementation jargon and secrets. Use the `repo-changelog` skill.
- Group changelog history by project version; keep new work under Unreleased.
  Calculate the next version once per release from Conventional Commits and
  surviving diffs since the last release or recorded baseline, not once per commit.
  Before 1.0, features or breaking changes bump the minor version; fixes alone
  bump the patch. Docs, tests and chores alone do not bump it. At 1.0 and above,
  breaking changes bump the major version. Do not invent release tags or dates.
- Run checks proportionate to the change. Environment installation does not run
  application checks; optional guardrail project checks require configuration.
- Role prompts, policies and tool names do not enforce permission boundaries.
