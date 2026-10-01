# Provenance

This release replaces the initial synthetic summaries with the installed sources.
`source-manifest.json` records the source path and SHA-256 of every copied file.
All copied files are byte-identical to their sources.

- autoresearch: installed Claude skill, including create/run references and templates.
- council: installed shared skill, including its transcript extraction script.
- sssf: resolved installed skill in the personal SSSF checkout, including cookbooks,
  references, templates, scripts and visualizer source; the full live engine is not bundled.
- factory-commands: installed Claude skill documenting the author's just recipes.
- workflow entry points: existing agentic-environment Markdown files.

Excluded: evaluation workspaces/transcripts, caches, bytecode, node_modules, built
dist, secrets, live factory state and provider settings. autoresearch-workspace is
an evaluation output directory, not a second installed skill.

Source instructions are retained even where they assume another installed skill
or a full local engine. The README states those dependencies rather than changing
behavior to make the export appear portable.

Earlier repository commits contain rewritten summaries and are superseded by this
source export. Research inspiration: Karpathy autoresearch; factory/fusion
inspiration: disler's agent workflow examples. This repository makes no claim to
have invented the underlying agent CLIs, Herdr, Pi or model families.
