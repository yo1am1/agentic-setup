# Sources and portability

`source-manifest.json` records every bundled file except itself, with paths relative
to `.agents/`, the original SHA-256 for imported files, the current SHA-256, and its
source. Files omitted from the minimal environment keep their original hashes under
`omitted`. `~/` identifies source locations at packaging time, not runtime
dependencies or links. Generated routing and packaging documentation is identified
as project-authored. No source archives or duplicate resource trees are included.

## Sources

- Installed `~/.agents/skills/{council,herdr,caveman,cavecrew,humanizer}`. Caveman
  lives in core `skills/caveman/`; the others live in `optional/`. Council
  installed instructions are newer than `~/VS/agentic-setup/.agents/skills/council`;
  installed wins.
- Installed `~/.agents/skills/caveman-commit/SKILL.md` is bundled in core
  `skills/caveman-commit/`, with the existing Caveman MIT notice. Its boundary
  distinguishes message-only requests from completing an authorized commit.
- `~/.agents/skills/specsmd-*`: twelve invocation wrappers, now
  `optional/specsmd/wrappers/<name>.md` (original hashes retained).
- `~/.specsmd/{simple,fire,aidlc,ideation}`: all 136 flow files, of the global
  installation's 138 regular files. Global `install-global.sh` and host-specific
  `manifest.yaml` are intentionally omitted; the global `skills` symlink is not
  copied. Installed version is 0.1.74.
- Cached npm `specsmd` 0.1.74 `package.json`: preserved as
  `optional/specsmd/upstream-package.json` for version, upstream URL, and dependencies.
- `~/VS/agentic-setup/licenses/caveman-MIT.txt`: retained as `skills/caveman/LICENSE`.
  Its routing/workflow and provenance documents informed the project-flow scope;
  no unrelated global policy or integration was imported.
- Existing project `.agents/agents/README.md`, `AGENTS.md`, and workflow index
  informed the startup contract and canonical procedure links.

## Adaptations

Specs.md home paths become repository-root-relative
`.agents/optional/specsmd/resources/` paths; the old global `/skills` alias resolves
explicitly to `resources/aidlc/skills`. Resources remain single-copy and wrappers
use them directly. Agent-local `skills/` paths retain agent-relative semantics.
Fixed the existing Operations `menu.md` reference to the supplied `navigator.md`,
marked the absent rollback procedure unavailable, and repaired the Inception
agent path in project-init, plus the Construction wrapper bolt-plan redirect
to its actual Inception resource. Commands change only to resolve vendored resources;
no workflow was executed.

Council's Caveman/helper locations now resolve in the repository. Council remains
Herdr-only with its original protocol and helper. Caveman gains the shared
startup requirement. Cavecrew gains a missing-preset disclosure and its README
no longer links to nonexistent native preset files. Humanizer gains the explicit
prose-only boundary and separate factual/voice evaluation, plus OpenAI metadata
and Claude frontmatter that disable implicit invocation. Humanizer version and
pattern content remain 3.1.0; this is a local project adaptation, not an upstream release.

Humanizer's README, CHANGELOG, AGENTS.md, plugin/CI metadata and package validator
are omitted: they are upstream packaging, not needed to use the skill.

## Licenses and limitations

Humanizer includes its original MIT license; Caveman's MIT notice is retained.
Specs.md's installed manifest and npm package declare MIT, but neither supplied
resource tree nor cached package contains a license text/copyright notice. That
notice was not invented; obtain the upstream notice before external redistribution.
Council, Herdr, and Cavecrew supplied bundles contain no license text; their
redistribution terms remain unverified. Source availability is not a license.
No web/license lookup was performed during this offline packaging task.

Cavecrew native role presets are absent. Skills do not register native commands,
agents, sandboxes, hooks, or integrations. Council's transcript extraction depends
on local CLI storage formats. Specs.md AI-DLC JavaScript helpers need `fs-extra`
and `js-yaml` resolvable by Node; dependencies were not installed or exercised.
The optional upstream AI-DLC documentation dump is not bundled; it is an external
reference, not an execution dependency.
