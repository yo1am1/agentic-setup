# Autoresearch Loop

Autonomous experiment loop. Read the target experiment's `program.md`, then iterate:
pick one change → create config → run → check metric → update results → repeat.

## Usage

```
@autoresearch-start.md @experiments/<experiment>/program.md
```

Examples:
```
@autoresearch-start.md @experiments/medical/program.md
@autoresearch-start.md @experiments/rag_chunking/program.md
```

---

## Before you start

1. Read the experiment's `program.md` — metric direction, YAML tunables, run command, Ideas to explore.
2. Read `results.tsv` — know the current champion before touching anything. The champion is the row with the best **primary metric** (col 1) and `keep` status; respect the metric direction (lower wins for loss/latency/bpb).
3. Check data exists — if `results.tsv` has only the header row (no data rows) and `prepare.py` exists, run it first. Confirm `logs/` exists (the run command redirects into it).

---

## The loop

```
1. Pick one change   — one variable at a time, motivated by prior results
2. Create config     — new YAML in configs/, descriptive name (e.g. lr_3e5.yml, epochs_8.yml)
3. Run               — command from program.md, redirect stdout+stderr to logs/<name>.log
4. Read result       — grep primary metric + status from the log (pattern in program.md)
5. Decide
     keep    → train.py already wrote the row; update Champion results in program.md
     discard → train.py already wrote the row; no further action needed
     crash   → append "crash" row manually to results.tsv; try a safer config
6. Repeat
```

`train.py` auto-appends to `results.tsv` and sets `status: keep` or `status: discard`.
Never edit results.tsv by hand except to append a crash row.

---

## Picking the next config

- Always start from the **champion config** (highest primary metric with `keep` status)
- Work through **Ideas to explore** in order unless prior results suggest a better direction
- Skip configs already in results.tsv
- Config name = what changed: `lr_3e5` not `run4`

---

## Stopping conditions

Stop when any of these are true, then report findings:

- 3 consecutive `discard` runs with no improvement
- All **Ideas to explore** exhausted
- User says stop
- Primary metric plateaued (< 0.5% gain over last 3 keeps). Note: a run that **ties** the champion is logged `keep` but is not progress — it counts toward the plateau.

Report: champion config + metric, summary of what worked/didn't, suggested next steps.

---

## Rules

- Never modify `prepare.py` during the loop — data must stay fixed for scores to be comparable
- Never change the MLflow experiment name — breaks model registry linkage
- Never re-run a config already in results.tsv
- One config at a time — no parallel runs
- Use `PYTHONUNBUFFERED=1` when redirecting to log files
- GPU experiments: verify no other GPU job is running (`nvidia-smi`)
- Ollama experiments: verify Ollama is running at localhost:11434 before starting
