---
name: feed-sync
description: Work on the XML product feed -> Pinecone sync in src/feed_sync. Use when changing which feed columns are synced, adding a customer feed, taking a customer live, validating or debugging a sync run, or reading its Mongo logs.
---

# Product feed sync

A background job per customer, started in `src/core/utils/lifespan.py`, runs once at
app start and nightly: download the XML feed, skip if nothing changed on either side,
otherwise compare mapped fields against Pinecone, back up, write the differences,
enrich new products, and record everything in Mongo.

`settings.feed_sync_test_mode` (`FEED_SYNC_TEST_MODE`, off by default) picks every
target at once: the test namespaces and a local MongoDB while on, the live namespaces
and the app's database once off.

## Module map

- `feed_sync/spec.py` — `FeedSpec`: the shape of one feed mapping.
- `feed_sync/<customer>.py` — one customer's mapping and its feed-specific rules.
- `feed_sync/tenants.py` — every customer: feed URL setting, spec, indexes, namespaces (by test mode), hints collection.
- `feed_sync/database.py` — the Mongo the sync writes to: local in test mode, the app's otherwise.
- `feed_sync/engine.py` — the run: gates, compare, backup, apply, state save. Never names a feed field.
- `feed_sync/state.py` — last clean run per target: feed hash and LSN watermarks (`FeedSyncState`).
- `feed_sync/lsn.py` — Pinecone write-log positions from response headers.
- `feed_sync/journal.py` — general log (`FeedSyncRun`) and business changelog (`FeedSyncChange`).
- `feed_sync/backup.py` — whole-index backups taken before any write.
- `feed_sync/short_description.py` — `ai_short_description`, written with every new or changed description.
- `feed_sync/enrichment.py`, `feed_sync/attributes.py`, `feed_sync/hints.py` — part 4: attributes to Pinecone, hints to the customer's hints collection, for products not enriched yet.
- `handlers/feed_sync.py` — admin API: the latest run of a customer, and approving a held run (runs in the app's background).
- `scripts/feed_sync_once.py` — one run by hand, optionally dry, or approving a held large diff.

## Invariants — never break these

1. The feed overwrites only fields its spec maps; every other Pinecone field is untouched.
2. An empty feed value never overwrites an existing value.
3. Products missing from the feed are logged, never deleted.
4. Order inside a run: general log entry, then gates, then compare, then backup, then writes, then enrichment, then state save. Nothing touches Pinecone before its general log entry exists.
5. A changelog entry is saved before its Pinecone write; if saving fails, the write must not happen.
6. Sparse is written before dense. Comparison reads dense, so dense must change last.
7. Both indexes are backed up and Ready before the first write; a failed or late backup fails the run with no writes.
8. Backup retention keeps the sync's backups for `PRODUCT_FEED_BACKUP_RETENTION_DAYS`, however many there are, and deletes only backups named with `BACKUP_NAME_PREFIX`; never widen it to backups the sync did not make, and a cleanup failure never fails the run. A run reuses a Ready sync backup made after the last clean state save instead of taking a new one, so runs that keep failing never let the backup from before their writes age out; a target with no clean run yet (go-live) reuses the oldest sync backup, which predates all of its writes.
9. State is saved only after a real, not held run with zero failed products, enrichment included.
10. Only exact equality of both LSNs with the saved watermark means Pinecone is unchanged; higher, lower, or unknown forces a full compare.
11. The feed hash and the comparison share one text normalization (`_comparable`); change them together or not at all.
12. The feed URL carries an access token: never log it, store it, or put it in an error message. Store only the host.
13. Open Pinecone through `connect_tenant`, never through the app's `UnifiedRetriever` singleton, which is bound to one index.
14. No module-level import from `core` inside `feed_sync`; every Mongo access goes through `feed_sync.database`, which imports `core.db` inside the function. A module-level import creates an import cycle through the app's lifespan.
15. The large-diff guard (`PRODUCT_FEED_MAX_CHANGED_FRACTION`) puts the run on hold instead of writing. A person reviews it (`GET /admin/api/v1/feed-sync/{tenant}/runs/latest`) and approves that held run (`POST .../approve` with `held_run_id`, or `feed_sync_once.py --approve-large-change HELD_RUN_ID`); the approved run applies only products the held run listed and holds again otherwise. Do not raise the limit to push a change through.
16. A product is enriched once it has a `category`. Enrichment only fills a product without one and never overwrites: hints the product already has in the hints collection are kept as they are, and an attribute that already has a value keeps it (a person may have curated both). New hints are saved before the attributes, so the attributes write marks the product done and any failure is retried by the next run.
17. The short description is part of the description change's own write: if it fails, the product's change fails and is retried.
18. Test mode never reaches live data: namespaces come from `tenants.py` and every Mongo record, hints included, from `feed_sync.database`; never bypass either.
19. Products run `PRODUCT_FEED_PRODUCT_CONCURRENCY` at a time; the steps inside one product keep their order. Write helpers return their LSNs and only the event loop records them (`SyncRun.record_writes`), so concurrent writes never lose the highest position.
20. Nothing blocking runs on the app's event loop: every Mongo write, Pinecone and HTTP call, catalog-wide CPU work and the LLM client setup go through `asyncio.to_thread`. On the loop, log steps with `await run.astep(...)` (pass the exception itself as `exc_info`); `run.step` is for code already in a worker thread.
21. One run per target at a time: a unique index on running `FeedSyncRun` documents refuses a second run (`RunInProgressError`) before it touches Pinecone. A run still `running` after `PRODUCT_FEED_RUN_STALE_HOURS` counts as killed and is closed by the next run; never close younger ones, they may be live on another instance.
22. A new product's vector id is derived from tenant and product id, so overlapping runs that add it write one record.

## Change which columns are synced

1. Verify the pairing on live data first: fetch the feed and the namespace, join on base product id, and measure per-field agreement after cleaning. Low agreement means a missing cleaner or a field that is not really the same thing.
2. Edit only the customer's spec module: `field_map` for one-to-one columns, `cleaners` for formatting noise, `group_metadata` for values built from all package-size rows.
3. Add a Pinecone key to `embedded_fields` only if it appears in `pinecone_helpers/text_template.py`; a test enforces this.
4. Never map a field whose Pinecone value is our own taxonomy or enrichment; the feed's version of it is not the same data.
5. Expect the first run after deploy to do a full compare: the hash covers the mapped output, so a mapping change changes it.

## Add a customer

1. Add the feed URL as an optional `SecretStr` in `src/config/settings.py` and to `.octopus/tfvars/common.tfvars.json`.
2. Add the customer's spec module following the existing one.
3. Add a `Tenant` in `configured_tenants`, with its own indexes, namespaces from `_namespaces()` and its own hints collection; never share a hints collection between customers.
4. Seed the test namespaces from the customer's real namespaces, run dry, then run for real, then run again and expect `no_changes`.

## Take a customer live

1. Dry-run with test mode off from a branch and read the would-be diff in the general log.
2. `FEED_SYNC_TEST_MODE` is `false` by default and in `common.tfvars.json`. Test mode is for local runs only: its MongoDB is `localhost`, which a deployed app does not have.
3. The state is keyed by customer plus indexes plus namespaces, so the first live run is a full compare by design; after a mapping or text-template change it usually goes on hold and needs one approving run.
4. The configured customer feed URL is set in `common.tfvars.json`, so every environment syncs into its own Pinecone index.
5. Approve the first held run in the deployed app through the admin API. `feed_sync_once.py` writes wherever the local `.env` points (it prints the targets and asks to type the namespace before a live write).
6. Every environment that syncs the same Pinecone namespace needs the same MongoDB; the one-run guard and the saved state live there.

## Validate a change

1. Unit tests: `uv run pytest tests/unit/feed_sync -q`. They stub all I/O; a slow run means a test reached a real service.
2. Live runs happen in test mode only (`FEED_SYNC_TEST_MODE=true`): test namespaces and the local MongoDB. Pass the feed URL as a process environment variable; never edit `.env`.
3. Prove the real namespaces were untouched by comparing their LSN before and after.
4. Every backup created while testing is tracked by id and deleted afterwards; verify the backup list matches its state before testing.
5. Cover: first run, immediate rerun (`no_changes`), a hand-edit in the test dense namespace (detected through the LSN), a dry run (no backup, no saved state), and a real run that restores the edit.

## Read and debug runs

- General log: one `FeedSyncRun` document per run, with ordered `steps`, `summary`, `status`, `error`. A failed run also stores `failed_step`, `error_type` and `error_at`; a failed product is its own step with the same fields. Every drift and new product is also a step, with full values.
- Status meanings: `no_changes` skipped by the gates; `succeeded`; `partial_success` some products written and some not, `summary.failed_products` lists each failure with its reason, state not saved; `hold` large-diff guard, nothing written, waiting for an approving run; `failed` the run raised, every product write failed, or it died midway (app restart, crash) and the next run of the same target closed it; `running` only while a run is in progress.
- The `Full compare needed` step lists why the gates did not skip, with current and saved hash and LSNs.
- Changelog: `FeedSyncChange` by `product_id` over time. A `pending` entry exists only while its write is in progress; one left by a run that died is closed as `failed` by the next run, whose compare re-applies the change. Values are stored whole: full old and new, and a `readable` diff of the whole text with changes marked in place.
- Backup ids are in the `Backup started` steps; restoring a Pinecone backup creates a new index, so prefer the changelog's old values for small reversals.

## Known limits

- Pinecone backup names allow only lowercase letters, digits, and hyphens.
- Backups: the sync's own backups are kept `PRODUCT_FEED_BACKUP_RETENTION_DAYS`; older ones are deleted after a new backup is Ready.
- General log and changelog expire after `PRODUCT_FEED_LOG_RETENTION_DAYS` through Mongo TTL indexes.
- Runs once at app start and nightly at `PRODUCT_FEED_SYNC_HOUR` in `PRODUCT_FEED_SYNC_TIMEZONE`.
- No alerts yet: outcomes are only in the Mongo logs.
- A dropped package size leaves its old `price_N` / `quantity_N` in Pinecone: updates merge metadata and cannot remove keys.
- Every drift is a step with full values in one `FeedSyncRun` document; about 4 MB per 1,000 changed products, against Mongo's 16 MB document limit.
- A run killed midway (restart, deploy) keeps its target locked until it is `PRODUCT_FEED_RUN_STALE_HOURS` old; runs in between fail with `RunInProgressError` and leave no run record.
