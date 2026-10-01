# SSSF Overview

The system map the orchestrator reads on startup — what SSSF is, how a stamped repo is laid out, and which cookbook to load next.

## What SSSF is

Super Simple Software Factory builds repeatable **agents plus code** workflows. Deterministic Python (an ADW script) owns sequencing, retries, and acceptance; agents are bounded nodes inside that graph. Agent proposes, code disposes.

Your job as orchestrator: **run the system, observe the system, help the engineer interact with it.** You do not do the work an ADW exists to do.

## Layout of an initialized repo

```
adws/
├── adw_sssf_config/
│   └── sssf.config.yaml         the agent roster — one agent, one prompt, one purpose
│   └── quality.json             real argv for static checks and tests; empty means fail
└── adw_data/
    ├── prompt_engineering/{agent}/{system.md,user.md}   tracked — edit prompts HERE, never in the skill
    │                                planner · test_writer · test_reviewer · builder · scout · reviewer · documenter
    ├── sessions/{adw_id}/                               gitignored runtime
    │   ├── agent_map.json       agent → coding-agent session_id + model
    │   ├── context_handoff/     the one place agents write files for the agents that follow
    │   └── {agent}/{prompts/, raw_output.jsonl, envelope.json}
    └── sssf.db                  gitignored SQLite trace db the visualizer polls
```

The ADW scripts and `adw_modules/` live once in `~/.claude/skills/sssf/templates/adws`.
The linked skill makes a machinery fix immediately active in every initialized
factory without copying or syncing files.

**v1 runs Pi only.** `coding_agent: pi`; the generated template defaults to `google/gemini-3.6-flash`, while this engine checkout's live roster defaults to `omniroute/claude/claude-sonnet-5` via `*m_builder`. Default thinking is `medium`. `claude_code` is specced in the config and stubbed in the interface — it lands in v2.

## The phase model

Every ADW run is a sequence of **phases**, each one `with run.phase(PhaseParams(...))`. Three kinds, three swim lanes:

- **engineer** — the human lane; today the system-input phase (who asked, and for what).
- **agent** — `ph.call(AgentCall(...))`: prompt in → typed envelope out → gates verified.
- **code** — deterministic steps that stand alone (git branch, git commit, migrate). Never buried inside an agent phase.

**Success must be earned — every phase defaults to `fail`.** A clean exit flips it to success; agent phases additionally require the envelope to parse and all gates to come back green. A raise keeps it failed, records an error event, and aborts the run. `retries=N` on an agent phase buys extra gate-correction rounds through the same session before that raise happens.

## Envelopes

Agents have exactly two output channels: reference files written into `context_handoff/`, and a **final valid-JSON response** parsed against the output type the call declared. Code persists it as `envelope.json` and injects it into the next agent's `user.md` via `{{previous_envelope}}`. Bad JSON is never a restart — the harness re-prompts the *same session, context intact*, until it parses (bounded). See `references/handoff.md`.

**The output contract is a synced triad**: the type in `data_types.py` ↔ the `## Report` JSON example in the agent's `user.md` ↔ `output_type=` at the call site. Editing any one of the three means editing all three in the same change — drift between them taxes every call with correction retries.

## Running the factory

```bash
just go
```

One command: it builds, starts the web app (`:4600`) and the dsh web UI
(`:3080`) as systemd user services, and prints where each is. Both are bound to
loopback; when Tailscale is up it also publishes them on the tailnet and prints
those URLs instead, so a phone on the same tailnet drives the factory with no
extra setup. `just status` repeats the URLs, `just logs` follows both, `just
kill` stops them; `just rebuild` rebuilds and restarts, so what you built is
always what is being served. Re-running `just go` is safe and idempotent.

Open the printed URL, then choose the project, harness, workflow, roster,
models when needed, and request. The web operator launches the shared ADW engine;
the same page shows its trace and output.

Reaching it over the tailnet publishes it to **every node in that tailnet**, and
the operator token is CSRF protection rather than authentication — any tailnet
peer can read it and launch a workflow that writes and commits. Fine for a
tailnet of your own devices; use tailnet ACLs otherwise. See
`references/observability.md` for how the fences work.

## When you have finished reading this

You are done with startup. Tell the engineer that `just init` initializes the
current repo and `just go` serves the web app and the dsh UI — on their tailnet
if it is up — then **wait for the engineer's request.**

Do not survey anything else — not the trace db, not the config, not past runs, not the repo tree. You do not yet know what the request is, so anything you gather now is a guess about what will matter, spent from the context the real work needs. Every cookbook and reference below is lazy-loaded, one per request, and that is the whole design.

## Where to go next

Load one cookbook per request — this overview is the only one you read up front.

| Request | Cookbook |
|---|---|
| Turn a request into the prompt an ADW gets | `how_to_prompt_for_the_eng.md` — **read before every launch** |
| Set the system up in a repo | `install.md` |
| Write a new ADW script | `create_adw.md` |
| Change an existing ADW chain | `update_adw.md` |
| Generate `sssf.config.yaml` | `create_config.md` |
| Add or retune an agent | `update_config.md` |
| Add low-level logic or a gate | `update_modules.md` |
| Run and monitor a workflow | `how_to_prompt_for_the_eng.md`, then `run_adw.md` |

References, loaded when you need the spec: `references/config.md` (full config schema), `references/handoff.md` (envelope + session layout), `references/observability.md` (events, db tables, polling).
