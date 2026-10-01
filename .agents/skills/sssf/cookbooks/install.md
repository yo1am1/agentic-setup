# Install

`just init` — link a repo to the shared SSSF engine.

## Run it

```bash
just init
```

Run from the **target repo root** — the cwd is where everything lands. If the skill lives in your user scope, the path is `~/.claude/skills/sssf/scripts/install.py`.

## What gets created

`install.py` **symlinks** the shared machinery to the software-factory checkout
that owns the skill, so every initialized factory runs the same code and the
same base config. Update the software-factory once and every linked repo
follows — no sync step, no drifted copies.

| Linked | To | Tracked? |
|---|---|---|
| `adws/adw_modules/`, `adws/adw_*.py` | the master's live workflow engine | yes (links) |
| `adws/adw_data/prompt_engineering/` | the master's prompts | yes (links) |
| `adws/adw_data/harness_engineering/` | the master's pi extensions | yes (links) |
| `adws/adw_sssf_config/*.yaml` | the master's base rosters | yes (links) |
| `justfile`, `.env.sample` | the master's copies | yes (links) |
| `adws/adw_sssf_config/quality.json` | detected from project manifests | yes — real file, per repo |
| `adws/adw_data/sessions/`, `adws/adw_data/sssf.db` | created at runtime | no — gitignored |

The two `*_engineering` links mirror the two config keys of the same name: `prompt_engineering` is what an agent is told, `harness_engineering` is what its harness can do. Edit them **in the software-factory**, and every factory sees the change at once.

`harness_engineering/` ships `subagents.ts` (the pi extension backing `subagent_create` / `_continue` / `_list` / `_remove`, wired to the planner and scout) and `graphify_query.ts` (semantic code-graph search for Fusion seats when the repo has a graphify index).

Repo-owned state is never linked: `quality.json` (detected per repo), `.env`,
sessions and the trace DB stay local and real.

## Idempotency and drifted copies

Re-running is safe: correct links are reported and left alone, and a link
pointing at the wrong target is repaired. An existing **real file or
directory** — a drifted copy from before linking — is reported and skipped
until you pass `--force`, which replaces it with the link. Commit anything you
want to keep first. `--copy` stamps real files instead of links, for a repo
that must keep working even if the software-factory checkout moves or is
deleted.

## Post-install checklist

1. **Env** — `cp .env.sample .env`, then set `OPENROUTER_API_KEY` in `.env`. (v1 runs Pi; `ANTHROPIC_API_KEY` / `CLAUDE_CODE_PATH` are only needed once Claude Code lands in v2.)
2. **Pi is installed and on PATH** — `pi --version`. Set `PI_PATH` in `.env` if it is not.
3. **The model resolves** — the config's default model must be a registered id in `~/.pi/agent/models.json`. Check with `pi --list-models` or read the file directly; see `references/config.md` for model resolution.
4. **Gitignore** — `install.py` appends `adws/adw_data/sessions/`, `adws/adw_data/sssf.db*`, and `.env` for you; confirm they landed. All three are runtime or secrets and must never be committed.
5. **Git repo** — SDLC workflows require the selected project to be a clean Git
   root because accepted work is committed.
6. **Smoke test** — start the app and run the smallest read-only workflow:

```bash
just go
```

It prints a URL per surface: a tailnet URL when Tailscale is up, otherwise
`http://localhost:4600`. `just status` reprints them; `just logs` shows why a
surface did not come up.

In the UI, select this project and **Scout**, then request “reply with a one-line
summary of this repo”. Green means the whole path works: config validated,
session minted, Pi ran, envelope parsed, and events landed in
`adws/adw_data/sssf.db`. Verify the trace exists before trusting anything larger:

```bash
sqlite3 adws/adw_data/sssf.db "select adw_id, status from sessions order by started_at desc limit 1;"
```

If the smoke test fails, fix it before composing chains — every multi-agent ADW rides on this exact path.
