# Run the loop

Autonomous: once started, keep iterating without asking between runs until a stop condition
is hit. The user can say stop at any time.

Input: `experiments/<name>/program.md` (the user names the experiment or points at the file).

## Before you start

1. **Read `program.md`** — metric direction, run command, grep pattern, tunables, Ideas to
   explore, Champion table, Change log.
2. **Read `results.tsv`** — know the champion before touching anything: the row with the best
   primary metric (column 1) and `keep` status, respecting the direction (lower wins for loss,
   latency, bpb). Also note every config already run.
3. **Check data** — if `results.tsv` has only the header row and `prepare.py` exists, run it
   first. Confirm `logs/` exists.
4. **Check requirements** listed in program.md Setup:
   - GPU: `nvidia-smi` — make sure no other GPU job is running.
   - Local services (e.g. Ollama at localhost:11434, a DB): verify they respond.
   - API keys: verify they're set (don't print them).
   If something is missing, stop and tell the user — a run that fails for an environmental
   reason wastes a run and pollutes the ledger.

## The loop

```
1. Pick one change   — one variable at a time, motivated by prior results
2. Create config     — new YAML in configs/, copied from the champion config, one key changed,
                       descriptive name (lr_3e5.yml, epochs_8.yml), description says what and why
3. Run               — command from program.md, stdout+stderr → logs/<name>.log
4. Read result       — grep primary metric + status from the log (pattern in program.md)
5. Decide
     keep    → train.py already wrote the row; update Champion table in program.md
     discard → train.py already wrote the row; nothing else
     crash   → append a crash row to results.tsv by hand; read the traceback;
               try a safer config (or fix a code bug — see Code changes)
6. Repeat
```

`train.py` appends to `results.tsv` and sets `keep`/`discard` itself. Only ever edit
`results.tsv` by hand to append a crash row: `<config>` in col 0, `-` for every metric/param
cell, `crash` as status, and a description containing the error. Hand-editing kept rows would
corrupt champion detection.

Long runs: run in the background and wait for the process to finish rather than polling the log
over and over.

## Picking the next config

- Always start from the **champion config**, so each keep compounds on the best so far.
- Work through **Ideas to explore** in order unless prior results point somewhere better — e.g.
  a winning direction deserves a follow-up step further (lr 3e-5 won → try 2e-5).
- Never repeat a config already in `results.tsv` — same config, same score, wasted run.
- Name configs after what changed: `lr_3e5`, not `run4`.
- When a result is surprising, read the log and diagnose before choosing the next change.
  Failure analysis (where does the metric lose points?) usually finds better next steps than
  blind sweeps.
- Diagnosis may inspect errors of configs already run, but never score untried configs on the
  eval set outside the loop (ad-hoc sweeps, scratch scripts). Every eval-set score must be a
  ledger row — off-ledger peeking selects configs on noise and leaves no record of the search.
- Add newly discovered ideas to **Ideas to explore** in program.md; strike through or annotate
  ideas that were tried, with the result.

## Code changes

Default: each run is a new YAML only. Editing `train.py` is allowed when a config can't express
the next idea (new strategy, new option, new metric) or to fix a crash bug. Rules:

- **Additive and default-off**: add a new tunable whose default reproduces the old behavior, so
  every earlier config still produces the same score. That keeps the ledger comparable.
- **Never touch the eval**: `prepare.py`, eval data, the metric computation, the train/val split.
  Changing those makes every prior score meaningless — that needs a new experiment, not a loop step.
- **Log every code change** in program.md under **Change log**: date, what changed in which
  file, why, which configs first used it. Also add the new tunable to **YAML tunables**.
- Re-run the champion config after a non-trivial code change if there's any doubt it still
  reproduces; name it `<champion>_repro`.

## Stopping conditions

Stop when any is true:

- 3 consecutive `discard` runs with no improvement
- All **Ideas to explore** exhausted
- The user says stop
- Primary metric plateaued: < 0.5% relative gain over the last 3 keeps. A run that **ties** the
  champion is logged `keep` but is not progress — it counts toward the plateau.

A crash is neither progress nor a discard; fix or skip it and continue.

## On stop: update and report

1. Update program.md: Champion table (config, primary, key secondaries, notes on the lineage),
   **Key findings** (what worked, what didn't, why), remaining Ideas.
2. Update the champion row in `experiments/README.md` (or wherever the project keeps its index).
3. Report to the user:
   - champion config + primary metric (baseline → champion)
   - what worked / didn't, in a few lines
   - code changes made (from the Change log)
   - suggested next steps (including expensive ideas outside this loop, e.g. new eval data)
   - **proposed commits**, grouped by round, Conventional Commits style, e.g.
     `feat(<name>): round 2 — seeds 10->5, healed boost (0.885 -> 0.920)`.
     Do not commit — wait for the user's confirmation.

## Rules

- Never modify `prepare.py` or eval data during the loop.
- Never re-run a config already in `results.tsv`.
- One run at a time — no parallel runs.
- `PYTHONUNBUFFERED=1` when redirecting to a log.
- Don't rename a tracking experiment (MLflow) mid-life.
- Never commit or push.
