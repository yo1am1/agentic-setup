# Provenance

`source-manifest.json` records each source origin, original SHA-256, exported
SHA-256 and exact text replacements. Unchanged copies have identical hashes.
Full instructions remain; there are no synthesized replacements for source skills.

## Sources

- Gewgur `.agents`: all 8 rules, 13 skills and their helpers, 4 workflows and
  2 role prompts. The full `AGENTS.md` becomes an optional backend profile.
- Installed autoresearch, Council and Herdr: complete skill bundles.
- Installed Caveman family: actual local versions and compression helpers;
  caveman-review is supplied from the installed Caveman plugin cache because
  the existing help prompt refers to it. MIT, Julius Brussee.
- Installed Ponytail 4.10.0: all six skill directories. MIT, DietrichGebert.
- Personal evaluation agents: all four full role prompts, including host metadata.
- Personal Fusion prompt templates: system, opinion, synthesis and vote text only.
- Agentic-environment research entry points: existing full Markdown workflows.
- Gewgur adapter generator: source-based, extended to include skill support files.

## Public configuration replacements

Jira cloud/account/instance identifiers, the repository remote, project summary
prefix, issue-key prefix, default parent epic and a Drive folder example become
configuration placeholders. A named customer becomes `configured customer`.
Procedure steps, constraints, code paths and test commands remain.
Replacement categories are recorded per file in the manifest; removed private
values are not repeated in the audit.

Fusion is a full invocation alias of the installed Council skill: only its name,
slash invocation, heading and helper installation path change. Research pattern
names and the complete consensus protocol are unchanged. The separate Fusion
JSON templates are preserved verbatim and are not confused with Council ballots.

Two original skill descriptions contained unquoted colons and were invalid YAML.
Only scalar quoting was corrected; their wording and full instructions remain.

The adapter extension copies every text support file alongside generated Claude
SKILL.md files. This fixes the source generator's missing-helper behavior; path-
scoped rules and role generation keep the existing implementation.

The README, routing overview and library AGENTS guide describe this publication;
they are not presented as copied source instructions. No live handovers, personal
transcripts, provider configuration, credentials, application code, factory engine
or UI are included. Historical commits are retained; the current tree reflects
this scope. Third-party skills are attributed, not claimed as original inventions.
