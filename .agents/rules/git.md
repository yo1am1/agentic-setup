# Git Rules

- Never commit or push automatically unless explicitly instructed.
- Never rewrite history (`rebase -i`, `commit --amend`, `push --force`) unless explicitly
  instructed.
- Never commit secrets, credentials, tokens, `.env` files, private keys, or generated/cache
  state.
- Before proposing a commit: run `git status --short` and `git diff`, and check for unrelated
  edits, generated files, secrets, and mixed concerns that should be split.
- Stage intentionally (`git add <file> ...`); avoid `git add -A` / `git add .` unless the full
  diff was reviewed.
- Run `make format && make test` (or the relevant subset) before proposing a commit; state
  plainly if a check was skipped or unavailable.
- Keep commits small and scoped to one concern; do not fold unrelated cleanup into a
  feature/fix commit.
- Commit message format follows `AGENTS.md` Git workflow: Conventional Commits, subject line
  only, no body, no trailers.
- Branch naming must strictly follow Jira Branching Model (`feature/PROJECT-<ticket>-...`, `bugfix/PROJECT-<ticket>-...`, `hotfix/PROJECT-<ticket>-...`, or `PROJECT-<ticket>-...` for other/chore); never use unmapped prefixes (`chore/`, `ci/`, `docs/`).
- If the working tree has unrelated user changes, do not overwrite them.
