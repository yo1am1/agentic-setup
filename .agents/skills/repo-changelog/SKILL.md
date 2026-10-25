---
name: repo-changelog
description: Generate end-user friendly release notes and changelogs from actual git diffs, consolidating related changes and identifying upgrade steps. Use for CHANGELOG.md updates, release summaries, or Slack release notes.
---

# Release notes and changelog

Read actual code and documentation diffs. Describe the final result for
users, rather than repeating commit subjects or internal implementation details.

## Choose the comparison

Honor the requested repository and range: two tags, changes since a tag,
a branch such as main, or the last N commits. Default to the current
repository and 50 commits only when no range was given. Detect the remote
without requiring GitHub; Bitbucket and local repositories work too.

For a pre-commit request, include the working tree and relevant untracked
files, and label the notes Unreleased. State which local reference was
used if local and remote branch references differ. Do not silently fetch,
push, publish, or commit unless the user authorized that action.

## Read and consolidate

- Read the full relevant diffs, including removed behavior, settings,
  documentation, and tests. Commit messages are context, not evidence.
- Check claims against the final code. Merge related changes; omit
  intermediate rewrites, reversals, and changes with no net effect.
- Describe what users can do, what works differently, and what they must
  change when upgrading. Avoid function names, variable names, and jargon
  in release bullets. Link to setup documentation for exact settings.
- Flag breaking changes that require user action, such as new login
  requirements, incompatible saved data, or renamed client commands.
- Never claim live behavior was tested when only offline checks ran.
- Never include secrets, private service addresses, or credentials.

## Write the notes

Update the repository's existing changelog if present. Preserve released
history and use its established order and headings. Use brief Markdown
bullets suitable for documentation or Slack. Include only relevant groups:

- New Features
- Enhancements
- Bug Fixes
- Changes
- Breaking Changes
- Others (including documentation)

Use one line per bullet where practical. Add short notes or links for
setup and known limitations. Do not invent a release version or date.

When repository rules require a changelog update on every commit, add an
accurate entry for each commit's own changes. Do not substitute unrelated
wording edits merely to touch the file.

## Tools and checks

Use the host's Git and filesystem tools directly. The supplied skill
description names optional analyzer/formatter scripts, but their source
was not supplied; this installation does not claim to bundle them.
No extra dependency is needed for this workflow.

Before finishing, check every release bullet against the comparison diff,
remove duplicates and technical implementation details, and verify that
upgrade instructions describe the final state.
