---
name: factory-commands
description: Which `just` recipe to run for the SSSF software factory, and what each one costs, writes, and commits. Covers the global justfile (stamp a factory, launch the multi-factory trace UI, list factories) and the per-repo justfile stamped into a factory (run ADW chains, read a run's trace). Use when the user asks how to run, stamp, or observe a factory, names a recipe like `just factory` / `just viz` / `just sdlc` / `just obs`, or asks which command does what and what it will change.
argument-hint: "[stamp a repo | watch runs | run a chain | read a trace]"
---

# Factory commands

Two justfiles, and which one answers depends on where you are standing.

| File | Reaches | Holds |
|---|---|---|
| `~/justfile` | any directory under `~` with no justfile of its own | the fleet: stamp a repo, list factories, run the UI |
| `<repo>/justfile` | that repo only, stamped by `install.py` | that factory: run chains, read its trace |

## Hard rule: the local justfile shadows the global one

`just` walks up from the cwd and stops at the **first** justfile it finds. A stamped repo has its own, so from inside one the global recipes do not exist:

```
$ cd ~/VS/software-factory && just viz
error: justfile does not contain recipe `viz`
```

That is not a broken install. Run global recipes from a directory that is **not** a stamped repo (`~`, `~/VS`), and per-repo recipes from inside the repo. `just factory` is the moment a repo flips from the first column to the second.

`just` with no arguments lists whatever is reachable from where you are standing — the fastest way to tell which of the two you have.

## The intended way in: an orchestrator, not a command

Per the skill's own docs, typing `uv run adws/...` is the fallback. Every
cookbook is addressed to an **LLM orchestrator** that reads `SKILL.md`, lists
the chains, waits for what you want, translates it into the four-line prompt
(`how_to_prompt_for_the_eng.md` — *"the intent is theirs, the precision is
yours"*), launches, watches, and reports back the prompt verbatim, the chain it
chose, and the `adw_id`.

| Recipe | Boots |
|---|---|
| `just cc` | Claude Code — or just type `/sssf` in a session you already have |
| `just pi` | pi, with the skill attached via `@file` so it is read, not searched for |
| `just codex` | Codex |

All three exist in **both** justfiles, because the local one shadows the global
one — so they keep working from inside a factory, which is where you want them
(the orchestrator reads `./adws` to know what it can launch).

**All three refuse to boot outside a factory.** A hidden `_factory-installed`
dependency runs `ls adws/adw_*.py` — the skill's own startup step 2 — and exits
1 before the agent starts:

```
$ cd ~/VS/some-plain-repo && just pi
no factory in /home/user/VS/some-plain-repo

install:  uv run ~/.claude/skills/sssf/scripts/install.py
     or:  /sssf install   (in a claude session)
error: recipe `_factory-installed` failed with exit code 1
```

Without it the boot succeeded and the model paid for the answer: pi loaded
`SKILL.md` in full, ran `pwd` and `find`, and reported "SSSF not installed
here" — a model boot and a skill's worth of context to learn what a glob knew
beforehand.

It tests the ADW scripts and **nothing else**, which is deliberate on both ends:

- Not `-d adws`, because an `adws/` with no `adw_*.py` has nothing to launch,
  and booting there spends exactly what the guard saves.
- Not the config path, because rosters are the engineer's to rename
  (`run_adw.md`). An earlier version also required
  `adws/adw_sssf_config/sssf.config.yaml`, which refused to boot in a working
  repo whose roster was called something else — a false negative on the very
  case the docs license.

**This gates only `just cc/pi/codex`, which are not an author entry point.** The
documented ways in are untouched and reach the orchestrator anywhere: `/sssf`
or `/sssf install` in a session, skill auto-match, or running
`claude`/`pi`/`codex` on the skill by hand. In an unstamped repo those still
boot and answer in one line, which is what `SKILL.md` specifies. The guard is a
shortcut on our own launcher, not a change to the factory's behaviour — which
is also why its message points at the author's install command rather than at
`just factory`, a recipe that lives only in the global justfile and so is
missing in exactly the half-stamped repo where the guard fires.

None bypass approvals. These chains spend real money and some commit to your
branch; the upstream example branch appends `--dangerously-skip-permissions` to
the Claude one, which is yours to add knowingly.

What the orchestrator may **not** do, per those docs: touch the application code
("you never research, touch, or dive into the codebase"), swap the roster on its
own, upgrade the chain you named, or survey the trace db before you have asked
for anything.

## Global recipes — run from `~` or `~/VS`

| Recipe | What it does | Reach for it | What it changes |
|---|---|---|---|
| `just factory` | stamps the factory into the **invocation directory** | once, per repo you want to automate | writes `adws/`, `.env.sample`, `justfile`, `.gitignore` entries. Idempotent — skips files that exist, so re-running doubles as a drift check. Touches nothing in git |
| `just factories` | every factory, its runs, cost, and URL | "what exists and where do I look" | nothing — reads the trace dbs directly, so it answers with the UI down |
| `just usage` | Codex quota left: % used, % remaining, reset countdown | before a long chain, or when a run dies unexplained | nothing — the usage endpoint is a metadata read, not a model call, so checking never spends quota |
| `just viz` | serves **all** factories at http://localhost:4600 | watching anything | starts a long-lived server and holds port 4600. Installs deps and builds `dist/` on first run |
| `just viz-build` | rebuilds the UI | after editing the visualizer's source | rewrites `dist/` |
| `just sync` | shows what the skill would push into **every** stamped factory | after changing anything under `templates/adws/` | nothing until you add `--apply` |

`just factory` stamps into wherever you invoked it, not into `~`. `cd` to the repo first.

### Keeping factories current

`just factory` (`install.py`) stamps once and then **skips every file that already
exists**, so a repo stamped last week never sees a fix made to the skill this
week. Its only other setting is `--force`, which `install.md` warns overwrites
*all* stamped files "including `sssf.config.yaml` and `prompt_engineering/`" —
the roster and prompts you tuned. `just sync` is the missing middle:

| | `install.py` | `install.py --force` | `just sync --apply` |
|---|---|---|---|
| new machinery file | added | added | added |
| changed machinery file | **skipped** | overwritten | **updated** |
| your roster / prompts / justfile | skipped | **overwritten** | never touched |
| your `quality.py` wiring | skipped | **overwritten** | reported, never touched |

Run it with no flags first — it reports and writes nothing. `--apply` refuses to
write into a repo with uncommitted changes (git is the undo) unless you pass
`--allow-dirty`. It never deletes, so your own `adw_*.py` chains are safe.

```bash
just sync              # every factory, report only
just sync --apply      # write the machinery updates
cd ~/VS/some-repo && just sync --apply   # just this one
```

## Per-repo recipes — run from inside a stamped repo

Sorted by what they cost you. **Every recipe below spends real tokens except the last group.**

| Recipe | Chain | Writes to the repo | Commits |
|---|---|---|---|
| `just demo` | scout twice, read-only | nothing | no |
| `just scout "…"` | `adw_scout` | nothing — `writes: []` is enforced, not promised | no |
| `just prompt "…" --agent NAME` | `adw_prompt`, one agent | whatever that agent is allowed | no |
| `just plan "…"` | `adw_plan` | `specs/` | no |
| `just ask AGENT "…"` | `adw_prompt` against a named agent | whatever that agent is allowed | no |
| `just plan-build "…"` | planner → builder → git | `specs/` + code | **yes, 1** |
| `just build-test "…"` | builder → deterministic test, bounded fix loop | code | no |
| `just build-review "…"` | builder → reviewer, bounded revise loop | code | no |
| `just sdlc "…"` | planner → builder → test → git | `specs/` + code | **yes, 1 — only if the suite is green** |
| `just simple-sdlc "…"` | plan → build → test → review → document | `specs/`, code, docs | **yes, 3** (plan, code, write-up separately) |
| `just document "…"` | `adw_document`, writes up the work from the git diff | docs | depends on the chain |

`just rosters` lists every roster in `adws/adw_sssf_config/` with each agent's
model (and whether it inherited it). `just kill` stops a run. `just ipi` is a
fourth orchestrator, guarded by `command -v` because `ipi` installs separately.

Three ADWs ship with no recipe — `adw_build.py`, `adw_quality.py`,
`adw_plan_build_test_quality.py`. Run them the raw way:
`uv run adws/adw_quality.py --config <roster> "…"`.

Reading a run costs nothing and never blocks a running one — the db is WAL:

| Recipe | Answers |
|---|---|
| `just sessions` | the last 10 runs, with status and cost |
| `just phases <adw_id>` | phase-by-phase status, in sequence |
| `just tail <adw_id>` | the live event tail |
| `just procs <adw_id>` | what that run has alive right now, with pids — how you find a hung agent |

Start with `just demo`. Green means the whole path works: config validated, session minted, agent ran, envelope parsed, gates checked, trace written. Fix it there before composing anything larger, because every chain rides that exact path.

## Ports

One process, http://localhost:4600, serving both the UI and the API for every
factory at once. `PORT=4700 just viz` moves it.

`just obs` inside a stamped repo is not a second server: it prints that repo's
deep link and delegates to the same global `viz`, so there is nothing to
collide with. (It used to boot a per-repo copy of the app out of
`.claude/skills/sssf/`, which `install.py` never stamps — so it failed in every
stamped repo until it was changed to delegate.)

## Quota

Every agent bills against one **weekly** Codex quota, so an exhausted
subscription kills a chain mid-run. `just usage` reads it live on each
invocation, and the factories page carries the same figure as a `codex 63% · 5d`
chip beside the live dot, refreshed every 5 minutes.

Both fall back to the last snapshot the `codex` CLI wrote to disk if the live
check fails, and say `cached (N old)` when they do — a stale number is never
passed off as current. Persistent `cached` means the token expired: run
`codex login`.

Note what does NOT refresh it: factory runs go through pi, which spends the same
quota but records nothing. Only the live check (or the codex CLI itself) moves
the number.

## Gotchas that cost real time

1. **A factory outside the scanned roots is invisible, with no error.** Discovery is depth-1 under `SSSF_FACTORIES_ROOT` (default `~/VS`), so a repo stamped anywhere else simply never appears — indistinguishable from a bug. The factories index names the roots it scanned for exactly this reason; if a repo is missing, check it is under one of them, or add its parent to the colon-separated list.
2. **Commit phases run `git add -A`.** Anything untracked and un-ignored in the tree lands in an agent's commit. Check `git status` before running a chain that commits — a stray `node_modules/` once put 5,198 files into one.
3. **`test` and `build` are theater until you wire them.** In `adws/adw_modules/quality.py` those two ship as `echo` placeholders that exit 0, so `sdlc` and `simple-sdlc` "pass" a suite that never ran. Replace their argv — it is the highest-value edit in a stamped repo. The other four blocks (`fmt`, `lint`, `deps`, `security`) ship **real**, because their invocation does not vary between Python repos; a missing binary surfaces as exit 127 rather than a quiet pass. This is also why `just sync` never overwrites `quality.py`: `update_adw.md` tells you to wire your command in there, so it is yours.
4. **Runs happen on your current branch.** No sandbox, no branch per run, no approval step. Branch first for anything you would not want committed where you are standing.
5. **A missing API key fails mid-chain, not at startup.** Validation checks that a model is written `provider/id`, never that its provider is reachable.

## Env overrides

| Variable | Affects | Use |
|---|---|---|
| `PORT` | `viz`, `obs` | move the UI off 4600 |
| `SSSF_FACTORIES_ROOT` | `viz`, `factories` | scan somewhere other than `~/VS`. Colon separated for several roots, like PATH: `~/VS:~/work`. Order is precedence — if two roots hold a repo of the same name, the first wins and the server logs which one it hid |
| `SSSF_CONFIG` | every per-repo chain | swap the whole agent roster for one run |
| `PI_PATH` | every chain | point at a `pi` binary that is not on PATH |

```bash
SSSF_CONFIG=adws/adw_sssf_config/sssf.frontier.config.yaml just sdlc "…"
```

## Chaining runs

`--adw-id` is optional on every chain. Omit it and a fresh id is minted and printed; supply it and the run **joins** that session — same dirs, same `context_handoff/`, and each agent resumes its existing context window instead of starting cold.

```bash
just plan "add a /health endpoint"                    # prints adw_id a1b2c3d4
just sdlc "implement the plan" --adw-id a1b2c3d4
```

Switching rosters mid-session breaks that resumption: `agent_map.json` pins the model each agent's session was created with, so a joined run whose config now names a different model starts that agent fresh.

## No `just` at all

Nothing depends on it — every recipe is one line. Open the justfile and run the line:

```bash
uv run adws/adw_prompt.py "say hello" --agent scout
sqlite3 adws/adw_data/sssf.db "select adw_id, status from sessions order by started_at desc limit 5;"
```
