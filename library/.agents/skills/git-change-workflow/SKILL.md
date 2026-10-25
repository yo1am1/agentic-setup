---
name: git-change-workflow
description: Apply when planning Git changes, creating branches, grouping commits, writing commit messages, or preparing PR summaries.
---

# Git Change Workflow

## Procedure

1. Inspect state first: `git status --short` and `git diff`. Check for existing user changes
   before editing; do not overwrite unrelated work.
2. Make focused changes only to files required by the task; avoid unrelated cleanup,
   formatting, or refactoring.
3. Review the diff again before staging: unrelated edits, generated/cache files, secrets,
   large files, mixed concerns that should be split into separate commits.
4. Stage intentionally — `git add <file> ...` for reviewed files. Avoid `git add -A` /
   `git add .` unless the full diff was reviewed.
5. Use the commit format from `AGENTS.md`: Conventional Commits, subject line only, <= 72
   chars, `type(scope): subject`, no body, no trailers.
6. Never commit automatically; commit only when explicitly requested. When asked to prepare
   a commit, report changed files and the proposed message. The pre-push hook
   (`make format && make test && make scan`) is the enforced gate before anything reaches
   the remote.
7. Never push, force-push, or rewrite history without explicit instruction.
