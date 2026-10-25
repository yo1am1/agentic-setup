# Sources and adaptations

The root `.agents/` directory is the primary environment. It was exported from
an actively used development setup at revision `a13169d07ceed83f810f0009a53920c49881b71f`.
`source-manifest.json` records each exported file's source, original SHA-256,
current SHA-256 and adaptations. The installer and tests retain their original
implementation; stack-specific guides become generic project guidance.

## Main environment

- Core Caveman, caveman-commit and project-flow instructions.
- Seven complete specialist roles and shared workflow/ownership contracts.
- Repository-local Claude, Codex and Gemini adapters, ownership tracking and tests.
- Complete optional Council, Herdr, Cavecrew, Humanizer and Specs.md resources.
- Optional, uninstalled Git guardrails; no application checks enabled by default.

The nested [upstream provenance](.agents/optional/PROVENANCE.md) records versions,
original sources, licenses and runtime/redistribution limitations. Caveman and
Humanizer notices are retained. Some supplied optional resources have unresolved
redistribution terms; this integration does not establish new rights to them.
No global configuration, credentials, application code, live session state or
provider runtime is included in the main environment.

## Preserved earlier library

`library/` retains the complete earlier instruction library, its original adapter
generator, validation scripts, source records, licenses and project profile.
Its source ledger uses paths relative to `library/`; the root ledger records those
same files under the `library/` prefix. Existing public-configuration redactions
and source hashes are preserved. It is reference material, outside root skill discovery.

## Authorship

Yehor Trepalin selected and merged the ingredients over time and assembled the main
setup in at most one day. Integration, routing, portability and verification are
separate from authorship of upstream skills. New README/demo/story documents and
root integration files describe this repository rather than claiming to be copied
upstream instructions. The source environment repository was not changed.
