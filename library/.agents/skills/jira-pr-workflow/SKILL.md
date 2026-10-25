---
name: jira-pr-workflow
description: "Automate the end-to-end task lifecycle: create/fetch Jira issue, checkout linked branch, develop, run quality gates, commit, push, create PR, and transition Jira status."
---

# Jira-to-PR Workflow Skill

Automates the complete development loop from Jira task creation to open GitHub Pull Request and Jira transition.

## Jira MCP Defaults

- **Cloud ID**: `<JIRA_CLOUD_ID>`
- **Instance URL**: `https://YOUR_ORG.atlassian.net`
- **Default Project Key**: `<JIRA_PROJECT_KEY>`
- **Default Parent Epic**: `<JIRA_PARENT_EPIC>` (configured project)
- **Default Assignee**: `<JIRA_ASSIGNEE_ACCOUNT_ID>` (configured assignee)
- **Story Points Field**: `customfield_10016` (Next-Gen estimate)
- **Allowed Issue Types**: `Task`, `Story`, `Bug`, `Epic`
- **Target Branch**: `master`
- **Repository Remote**: Bitbucket (`https://bitbucket.org/<WORKSPACE>/<REPOSITORY>.git`)

---

## Lifecycle Steps

### 1. Jira Issue Resolution (Create or Fetch)

- **Summary Convention**: MUST follow `[PROJECT][<Scope>] <Title Case Description>` or `[PROJECT] <Title Case Description>` format.
  - Project Tag: `[PROJECT]` (mandatory prefix for this repository).
  - Scope Tag (optional): `[<Scope>]` describing area/domain (e.g. `[Agents]`, `[Supervisor]`, `[Products]`, `[Retrieval]`, `[Refactor]`, `[Skills]`, `[Config]`, `[Prompts]`).
  - Title: Written in **Title Case** with spaces — major words capitalized, minor words (articles, conjunctions, short prepositions like `to`, `for`, `in`, `and`, `of`, `with`) in lowercase.
  - Examples:
    - `[PROJECT][Agents] Add Automated Jira-to-PR Pipeline Skill and Workflow`
    - `[PROJECT][Supervisor] Optimize Greeting and Onboarding Flow`
    - `[PROJECT][Refactor] Centralize Model Configurations in SSOT Registry`
    - `[PROJECT] Reduce TELL_MORE Product Description Length by 50%`
- **Mode A (New Task / Prompt-to-PR)**:
  - Formulate structured summary using `[PROJECT][<Scope>] <Title Case Description>` and clear markdown description (with Goal, Scope, Deliverables, and Acceptance Criteria).
  - Call MCP `createJiraIssue`:
    - `cloudId`: `"<JIRA_CLOUD_ID>"`
    - `projectKey`: `"<JIRA_PROJECT_KEY>"`
    - `issueTypeName`: `"Task"` (or `"Story"` / `"Bug"`)
    - `parent`: `"<JIRA_PARENT_EPIC>"`
    - `summary`: `"[PROJECT][<Scope>] <Title Case Description>"`
    - `assignee_account_id`: `"<JIRA_ASSIGNEE_ACCOUNT_ID>"`
    - `description`: Markdown content with background and acceptance criteria
  - If Story Points specified: call `editJiraIssue` with `fields: {"customfield_10016": <story_points>}`.
  - Record the returned issue key (e.g., `PROJECT-1659`).

- **Mode B (Existing Task / Ticket-to-PR)**:
  - Call MCP `getJiraIssue(cloudId="<JIRA_CLOUD_ID>", issueIdOrKey="PROJECT-123")`.
  - Extract summary, requirements, and acceptance criteria.
  - Optionally transition status to "In Progress" via `transitionJiraIssue`.

### 2. Git Branch Creation & Jira Development Panel Visibility

- **Branch Naming Standard** (Mapped to Jira Cloud / Bitbucket Branching Model):
  | Jira Branch Type | Format Pattern | Example |
  | :--- | :--- | :--- |
  | **Feature** | `feature/PROJECT-<ticket>-<short-description>` | `feature/PROJECT-1659-reduce-tell-more-prompt-length` |
  | **Bugfix** | `bugfix/PROJECT-<ticket>-<short-description>` | `bugfix/PROJECT-960-fix-product-size-responses` |
  | **Hotfix** | `hotfix/PROJECT-<ticket>-<short-description>` | `hotfix/PROJECT-968-fix-query-classification` |
  | **Other (Chore / Task)** | `PROJECT-<ticket>-<short-description>` | `PROJECT-1629-add-dockerignore` |

- **CRITICAL INVARIANT**: Never invent unmapped prefixes (e.g. `chore/`, `ci/`, `docs/`, `refactor/`). Bitbucket/Jira only binds branches matching `feature/`, `bugfix/`, `hotfix/`, or direct key slugs (`PROJECT-...`). Using unmapped prefixes prevents the branch from appearing in the Jira **Development** panel.
- **Development Panel Lifecycle**:
  1. **In Progress**: When branch is pushed to remote, Jira automatically shows `1 branch` and `N commits`.
  2. **In Review**: When PR is created, Jira shows `1 pull request OPEN`.
  3. **Merged**: When PR is merged to `master`, the remote source branch is deleted, and Jira updates to `1 pull request MERGED`.

- Create and switch to the branch off `master`:
  ```bash
  git checkout -b feature/PROJECT-<ticket_number>-<short-description> master
  # or for chores/tasks (Type: Other):
  git checkout -b PROJECT-<ticket_number>-<short-description> master
  ```

### 3. Implementation & Validation

- Apply focused code changes adhering to `AGENTS.md` and repository standards.
- If prompt changes were made:
  - Push updated prompt text to LangSmith Hub across environments:
    ```bash
    uv run python scripts/migrate_prompts_to_langsmith.py --prompt <key> --env dev
    uv run python scripts/migrate_prompts_to_langsmith.py --prompt <key> --env stage
    uv run python scripts/migrate_prompts_to_langsmith.py --prompt <key> --env preprod
    uv run python scripts/migrate_prompts_to_langsmith.py --prompt <key> --env prod
    ```
- Run focused tests for fast feedback:
  ```bash
  uv run pytest -m "not slow and not integration and not langsmith" -k <focused_name>
  ```
- Run the full mandatory pre-push gate:
  ```bash
  make format
  make lint
  make test
  make scan
  ```

### 4. Intentional Staging & Commit

- Review diff: `git status --short` and `git diff`.
- Stage explicitly: `git add <changed_files>`.
- Commit format (enforced by commit-msg hook):
  - `type(scope): subject` (<= 72 chars, no body, no trailers).
  - Example: `feat(prompts): shorten tell_more description length by 50%`

### 5. Push & Bitbucket Pull Request Creation

- Push branch to remote:
  ```bash
  git push -u origin <branch_name>
  ```
- Bitbucket generates the Pull Request link automatically in output:
  `https://bitbucket.org/<WORKSPACE>/<REPOSITORY>/pull-requests/new?source=<branch_name>&t=1`
- Present the clickable PR link to the user and in the Jira task comments.

### 6. Jira Status & Description Update

- Update Jira Description Acceptance Criteria checkboxes to `[x]` using `editJiraIssue`.
- Post a verification comment using `addCommentToJiraIssue` containing:
  - Branch name
  - Commit SHA & message
  - Bitbucket Pull Request link
  - LangSmith Hub sync confirmation (if applicable)
  - Test and security scan results summary
- Call MCP `transitionJiraIssue` to advance the issue (e.g. to "review" / "In Review").
