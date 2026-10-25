# Review

1. Read the [role contract](../agents/README.md) and
   [code reviewer](../agents/code-reviewer.md). Load [Caveman](../skills/caveman/SKILL.md) communication
   instructions unless the user selected another style. This is a read-only
   assignment, including through shell commands or external tools.
2. Establish the exact review target: working diff, staged tree, commit range,
   or integrated branch. Inspect both `git diff` and `git diff --staged` when
   reviewing uncommitted work. Record the target revision and scope; recheck if
   concurrent edits move it. Do not imply a staged review covered unstaged edits.
3. Read connected implementation, callers, contracts, and relevant tests. Check
   correctness, security, compatibility, validation, data handling, and stated
   requirements. Project instructions determine conventions and required checks.
4. Report only actionable defects or material requirement gaps. Each finding
   includes severity, file and line, triggering conditions, impact, and the
   smallest safe fix. Separate blockers from optional improvements. A missing
   defect finding is not evidence that unrun checks passed.
5. State observed checks and limits. Run only checks compatible with the read-only
   assignment and authorized environment; do not install dependencies, reformat,
   or update snapshots as part of review. Ask the implementation owner to fix
   findings; review authorization alone does not permit repairs.

Use [devil's advocate](../agents/devils-advocate.md) only for consequential
assumptions and [simplifier](../agents/simplifier.md) for demonstrated complexity.
A simplifier can propose deletions during review; implementation needs explicit
write scope and revalidation. [Humanizer](../optional/humanizer/SKILL.md) applies only to explicitly selected prose.
Team results need a fresh review after integration, not only worker reviews.
