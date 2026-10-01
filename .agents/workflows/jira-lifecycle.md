# Workflow: Jira Task Lifecycle

1. **Jira Issue Setup**:
   - Create new task with `createJiraIssue` (project `<JIRA_PROJECT_KEY>`, markdown description) OR fetch existing task with `getJiraIssue`.
   - Identify Jira ticket key (e.g., `PROJECT-123`).
2. **Branch Creation**:
   - Create and checkout branch strictly matching Jira Branching Model:
     - Feature: `feature/PROJECT-<ticket>-<short-description>`
     - Bugfix: `bugfix/PROJECT-<ticket>-<short-description>`
     - Hotfix: `hotfix/PROJECT-<ticket>-<short-description>`
     - Other / Task / Chore: `PROJECT-<ticket>-<short-description>` (never use `chore/`, `ci/`, `docs/`)
   - Branch off `origin/master`.
3. **Inspect & Plan**:
   - Inspect existing implementation and tests.
   - Plan minimal safe patch.
4. **Code & Validate**:
   - Apply code changes.
   - Run focused unit tests: `uv run pytest -m "not slow and not integration" -k <name>`.
   - Run pre-push quality gate: `make format && make lint && make test && make scan`.
5. **Commit & Push**:
   - Stage reviewed files (`git add <files>`).
   - Commit: `type(scope): subject` (<= 72 chars, no body, no trailers).
   - Push to remote: `git push -u origin <branch_name>`.
6. **Pull Request & Jira Sync**:
   - Create PR pointing to `master` with Jira link in description.
   - Transition Jira issue or comment with PR link.
