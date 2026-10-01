# Observability Reference

The event schema, the seven SQLite tables, and the polling contract — the one data path is **agents → sqlite → web ui**.

## Two stores, one truth

**Files are the raw record** (`raw_output.jsonl` streams, `envelope.json`, `agent_map.json`); **SQLite (`sssf.db`) is the queryable mirror** the UI reads. `tracer.py` writes both. Losing the db loses nothing that can't be rebuilt from files.

Location comes from `observability.db` in `sssf.config.yaml`, default `adws/adw_data/sssf.db` — inside the **target** repo, gitignored.

## Event schema

`tracer.py` emits these types, every one logged against its `adw_id` **and** `phase_id`:

| Type | Emitted when |
|---|---|
| `phase_start` | a `run.phase(...)` block is entered |
| `agent_start` | a coding agent is spawned or resumed for `ph.call(...)` |
| `tool_call` | a tool (`read`, `bash`, `edit`, `write`) returns — **one event per real call**, named `bash: ls -la src`, payload `{tool, tool_call_id, args, result_snippet, ok, duration_ms, agent}` |
| `handoff` | an envelope crosses from one agent to the next |
| `gate_pass` | a gate found no failed checks — payload carries `attempt`, `checks` (the evidence), and an empty `violations` |
| `gate_fail` | a gate found at least one failed check — payload carries `attempt`, `checks`, and `violations` |
| `log` | an explicit `ph.log(...)` from the ADW script |
| `agent_end` | the agent's run completes; envelope parsed or not — payload carries `cost`, `usage` (the per-component breakdown), `context_tokens`, `context_window` |
| `phase_end` | the block exits; carries the resolved status |
| `error` | a raise inside a phase block |

`parent_id` nests spans, so an agent phase expands into its tool-call spans in the UI.

**Spend is itemised per phase.** `agent_end.usage` carries tokens *and* dollars for each component pi reports — `input`, `output`, `cache_read`, `cache_write` — summed across every send the phase made, so a phase that retried on a bad envelope or a failed gate shows what all its attempts cost, not just the last one. The four components sum to `total_tokens`, and their costs sum to `total_cost`; the visualizer's Cost panel renders them as a table you can add up by eye.

`reasoning_tokens` is the thinking share and is **inside** `output_tokens`, not a fifth component — measured across every session on disk, reasoning never exceeds output and the four components always reconcile to the total. It bills at the output rate, so the panel nests it under output rather than adding it. Runs predating the breakdown have no `usage` key at all; the lump `cost` and the event's own `tokens` still stand, and the UI says so rather than rendering zeroes.

**Context is occupancy, not spend.** `events.tokens` and `sessions.total_tokens` bill every turn, so they only grow — an agent that burned 100k tokens may be sitting in a 15k window. `context_tokens` is how full the window actually was when the agent stopped, which is what the visualizer's per-lane Context bar measures against `context_window`.

It is computed the way pi computes it for its own footer and its auto-compaction trigger (`calculateContextTokens` in the coding agent's `core/compaction/compaction.ts`): take the last *valid* assistant turn — skipping `aborted` and `error` turns — and read `usage.totalTokens`, falling back to `input + output + cacheRead + cacheWrite`. Cache reads count; cached prompt is still prompt. `context_window` is the same `contextWindow` pi reads from `~/.pi/agent/models.json`, so `context_tokens / context_window` is the number pi would show. Both are NULL on rows written before the columns existed, and the lane draws no bar rather than a misleading empty one.

Two caveats worth knowing. Pi adds an *estimate* for any messages trailing the last assistant usage; in a batch (`-p`) run the session ends on that message, so the two agree. And if auto-compaction fires as the very last act of a run, the recorded number is the pre-compaction size — pi itself reports `null` in that window rather than guessing.

**Gates record evidence, not just a verdict.** A gate returns one `{item, ok, note}` check per thing it looked at, and `violations` are derived from the failed ones. Both land in `gate_results` (`checks_json` + `violations_json`) and in the `gate_pass`/`gate_fail` payload, so a green gate can answer *what did you verify* — `{"item": "…/plan.md", "ok": true, "note": "exists, 454B"}` — rather than only *did it pass*. Rows written before this existed have `checks_json` NULL; treat that as "no evidence recorded", not "nothing checked".

The gate event payload carries `attempt` too, so the `gate_results` table and the event stream are equivalent sources — a live consumer can group gate results per correction round from events alone, without a second query.

**A `tool_call` is the one event that spans time**, so it fills both `started_at` and `ended_at` on the row — the tool's real start and return. Every other type is a point in time: `started_at` is when it was recorded and `ended_at` stays NULL. Lay tool calls out on a time axis from those columns, never by parsing `payload_json` (`duration_ms` is in the payload too, as pi's own number, but it is a convenience, not the source for layout).

**Streaming is solved by construction.** `agent_pi.py` tails pi's JSONL stdout line by line and the tracer inserts each event into `sssf.db` **while the agent is still working** — never batched at phase end (verified in the first smoke run: tool calls visible mid-run). Everything downstream is a poll → render.

## Tables

```sql
sessions (
  adw_id        TEXT PRIMARY KEY,
  request       TEXT,              -- the engineer's ask
  status        TEXT,              -- running | success | fail
  engineer      TEXT,
  started_at    TEXT, ended_at TEXT,
  total_tokens  INTEGER, total_cost REAL
);

phases (
  phase_id      TEXT PRIMARY KEY,
  adw_id        TEXT REFERENCES sessions,
  seq           INTEGER,
  name TEXT, kind TEXT, owner TEXT, description TEXT,
  status        TEXT DEFAULT 'fail',   -- success must be earned
  attempt       INTEGER DEFAULT 0, retries INTEGER DEFAULT 0,
  error         TEXT,
  started_at    TEXT, ended_at TEXT
);

events (
  event_id      TEXT PRIMARY KEY,
  adw_id        TEXT REFERENCES sessions,
  phase_id      TEXT REFERENCES phases,   -- every event logs against adw + phase
  parent_id     TEXT,                     -- span nesting
  type          TEXT,   -- phase_start | phase_end | agent_start | agent_end | tool_call
                        -- | handoff | gate_pass | gate_fail | log | error
  name          TEXT,
  payload_json  TEXT,
  tokens        INTEGER,
  started_at    TEXT, ended_at TEXT   -- ended_at set only on events that span time
);

envelopes (
  envelope_id   TEXT PRIMARY KEY,
  adw_id        TEXT REFERENCES sessions,
  phase_id      TEXT REFERENCES phases,
  agent         TEXT,
  output_type   TEXT,              -- name of the data_types model it parsed against
  payload_json  TEXT,
  valid         INTEGER,
  attempt       INTEGER,
  created_at    TEXT
);

gate_results (
  id            INTEGER PRIMARY KEY,
  adw_id        TEXT REFERENCES sessions,
  phase_id      TEXT REFERENCES phases,
  attempt       INTEGER,
  gate          TEXT,
  passed        INTEGER,
  violations_json TEXT,             -- derived: the failed checks, as "item: note"
  checks_json   TEXT,               -- [{item, ok, note}] — everything the gate looked at
  created_at    TEXT
);

processes (                        -- adw_id → pid, so a stuck run can be stopped
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  adw_id        TEXT REFERENCES sessions,
  kind          TEXT,               -- 'adw' (the workflow process) | 'agent' (a coding-agent child)
  name          TEXT,               -- '' for the adw, the agent name for a child
  pid           INTEGER,
  command       TEXT,               -- what the pid WAS; pids get recycled, so verify before killing
  started_at    TEXT, ended_at TEXT -- ended_at NULL = believed alive
);

agent_sessions (                   -- the queryable mirror of agent_map.json
  adw_id        TEXT REFERENCES sessions,
  agent         TEXT,
  coding_agent  TEXT, model TEXT, color TEXT,   -- color: the config's lane swatch
  session_id    TEXT,
  context_tokens INTEGER,           -- window occupancy after the agent's last turn
  context_window INTEGER,           -- the model's ceiling, from the pi registry
  created_at    TEXT, last_used_at TEXT,
  PRIMARY KEY (adw_id, agent)
);
```

**A hung agent emits nothing**, which is exactly when you need its pid: no events,
tokens, or output. `processes` is the authoritative table; inspect live rows and
signal children before the parent only after the recorded command still matches
the PID. A killed run finalizes its own trace: SIGTERM and SIGINT become
`SystemExit`, so the session lands on `fail` with process rows closed.

**Derived, never stored:** phase durations (`ended_at − started_at`), session phase-progress (query `phases` by `adw_id`), lane layout (`kind` + `owner`).

Phase status invariants: `queued` only for manifest-declared phases not yet entered (dashed in the UI); `running` on enter; only a clean exit writes `success` — agent phases additionally need the envelope parsed and gates green; everything else resolves to `fail`.

## WAL pragmas

Open **every** connection — writer and reader — with:

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=5000;
```

WAL allows readers during writes. Writers are the tracers of running ADW processes; concurrent writers are fine given one small transaction per event plus `busy_timeout`. The visualizer reads on a readonly connection with exactly one exception: archiving a session (`POST /api/sessions/:adw_id/archive`) opens a second connection to set `sessions.archived`. That flag is review triage — it says a human has looked at the run — so it is the reader's state living on the row, and no tracer ever writes or reads it.

## Polling contract

**The UI never receives pushes.** No ingest endpoint, no WebSocket, no backfill or dedup logic.

Live view polls on a rowid cursor every `observability.poll_ms` (default 500):

```sql
SELECT ... FROM events WHERE adw_id = ? AND rowid > ? ORDER BY rowid LIMIT 500;
```

Keep the highest `rowid` returned as the next cursor. History is **the same queries** with filters, lazy-paged as the engineer scrolls or drills in — one mechanism serves both live and past runs, which is why there is no separate replay path.

## Reading a model's own output, not just its name

An envelope or a `ph.log()` names a path constantly — `EnvelopeBase.artifacts`,
`plan_path`, `document_path`, `ScoutFinding.file`, Fusion's own `report`/`plan`
kwargs to `ph.log()` at consensus time — but a name in a JSON dump is not the
file. `highlightJsonPaths` (`src/lib/highlight.ts`) turns a string value under
a path-shaped key into a clickable button; `PhaseDetail.vue` and `FileViewer.vue`
wire one delegated click handler each to open it in the shared repo browser
(`viewPath`/`@navigate`), so a `.json` file's own path fields chain to the next
file the same way. `FileViewer` then renders `.md` through the same
`renderMarkdown` the compiled-prompt panel already used, and `.json` through
`highlightJsonPaths` again — both with a rendered/raw toggle; everything else
stays the plain-text view it always was.

**The precision problem, and how it's solved.** A model id
(`omniroute/codex/gpt-5.6-luna-medium`) contains slashes too, and a plan's own
Markdown content sometimes reuses the very key (`plan`) that a log event uses
for the path to it — a shape check alone or a key check alone both misfire.
`highlightJsonPaths` requires both: the key must be one this engine actually
uses for a path (`PATH_KEYS` in `highlight.ts`, grounded in a repo-wide grep of
every envelope and `ph.log()` field, not guessed), and the value must be
short, single-line, and shaped like a path rather than a URL. Key tracking is a
flat "last key seen" pass over the token stream, not a real object walk —
pretty-printed JSON always emits a key immediately before its value, and that
survives nesting well enough for an array of paths under one key or a path
field inside an array of objects. See `src/lib/highlight.test.ts` for the
false-positive cases this is checked against (a model id, a sibling key, the
`plan`-as-content-vs-`plan`-as-path ambiguity itself).

## Serving the UI, and reaching it from a phone

`just go` runs `scripts/services.py up`, which renders two systemd **user**
units from `templates/systemd/`, starts them, and publishes each on the tailnet
with `tailscale serve --bg --http=<port> <port>`:

| Surface | Port | Unit |
|---|---|---|
| Software Factory web app | 4600 | `sssf-visualizer` |
| dsh web UI | 3080 | `dsh-web` |

Both stay bound to **loopback**. Serve proxies the tailnet to them, so nothing
is offered to the LAN and Funnel is never involved. With `loginctl
enable-linger` set, both come back after a reboot with no terminal involved.

### The Host fences

Each surface independently checks the request's `Host` against a literal
allowlist, and they must agree or the symptom is a bare 403 that reads like a
DNS fault:

- **visualizer** — `SSSF_TRUSTED_HOSTS`, comma-separated `host:port`, read per
  request by `guardOperator` in `server/operator.ts`. Unset means the fence is
  exactly loopback-only, which is the default and the behaviour with Tailscale
  down.
- **dsh** — repeated `--trusted-host <authority>`.

`scripts/tailnet-authorities.sh <port>` is the single producer of that list
(MagicDNS name, its short form, each Tailscale IP literal). It prints nothing
and exits 0 when Tailscale is down, so a unit starts loopback-only rather than
failing to start.

Both fences receive the list **once, at launch**. Bringing Tailscale up after
the services are running therefore leaves them correct but unreachable, so `up`
reads `/proc/<pid>/{cmdline,environ}` and restarts a surface that is missing an
authority it now needs. `up` restarts for exactly two reasons — a re-rendered
unit, or that missing authority — and otherwise only starts what is down.

### Access control

`tailscale serve` publishes to the **whole tailnet**, and the operator token is
CSRF protection, not authentication: any tailnet peer can `GET /api/operator`,
read the token, and `POST` a launch that writes and commits. The trace and file
read APIs need no token at all. Appropriate for a tailnet of your own devices;
restrict the node with tailnet ACLs otherwise. Serve carries plain HTTP inside
the WireGuard tunnel, which makes the page a non-secure browser context, so
clipboard-copy buttons fail there (guarded, so nothing else degrades).

### Two systemd traps these units already avoid

- **`$` in `ExecStart` is a systemd specifier**, expanded before the shell runs;
  `${args[@]}` became an empty string and reached dsh as a stray argument. Every
  shell `$` in the templates is written `$$`, and both units set
  `StartLimitBurst=5` so a bad config stops instead of hot-looping.
- **Nothing may depend on the invocation directory.** dsh's `WorkingDirectory`
  is `$HOME`, not the factory `just go` ran in: a per-factory unit is rewritten
  and restarted on every `just go` elsewhere, and dsh refuses to boot in a
  directory whose `.env` sets a code-loading variable such as `PYTHONPATH`.
  Browser sessions pick their project in the dsh UI, so cwd is only a default.
