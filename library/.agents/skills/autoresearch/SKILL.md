---
name: autoresearch
description: "Autonomous experiment loop for any project — scaffold a measurable experiment (one primary metric, frozen eval data, one YAML config per run, results.tsv ledger) and then run it hands-off: change one thing, run, compare against the champion, keep or discard, log, repeat until plateau. Use this whenever the user wants to set up an experiment, benchmark or tune something iteratively (hyperparameters, prompts, retrieval/RAG settings, chunking, latency, cache config, model fine-tuning, red-teaming), says \"autoresearch\", \"experiment loop\", \"start the loop\", \"create an experiment\", \"keep iterating until it stops improving\", \"run overnight and find the best config\", or points at an experiments/<name>/program.md — even if they don't say \"skill\" or \"autoresearch\"."
---

# Autoresearch

Greedy local search over a config space, run by the agent itself. A **champion** (best run so far)
is the incumbent; each run changes one variable; the run is kept only if the primary metric
matches or beats the champion; the loop stops when progress plateaus.

Anything measurable fits: model training, retrieval pipelines, prompt tuning, API latency,
cache hit rate, red-teaming a system prompt, page load time.

## Two modes

| User intent | Mode | Read |
|---|---|---|
| "create/set up an experiment for X", "I want to measure/tune X" | **Create** | `references/create-experiment.md` |
| "start/continue the loop", "run experiments on `experiments/<name>`", points at a `program.md` | **Run** | `references/run-loop.md` |
| "create it and run it" | Create, verify baseline, then Run | both, in order |

Read the matching reference file before acting — it has the exact steps, templates and rules.
Templates live in `templates/` next to this file (`train.py`, `program.md`, `baseline.yml`,
`experiments_readme.md`).

## The contract (what makes the loop work)

Every experiment needs exactly three things. If one is missing, the loop can't run honestly —
ask the user rather than guessing.

1. **One scalar primary metric** with a stated direction (higher/lower is better), computed on
   a fixed eval set. Secondary metrics are optional diagnostics (cost, time, overfit signal).
2. **A parameterized run command**: `train.py --config configs/<name>.yml` that prints
   `config:`, `<primary>:`, `status:` to stdout and appends one row to `results.tsv`.
3. **Frozen eval data**: produced once (by `prepare.py` if needed) and never changed during a
   loop — otherwise scores from different runs aren't comparable.

## Standard layout (in the target project)

```
experiments/
├── README.md          — index: one line per experiment + champion table
└── <name>/
    ├── train.py       — the run script: --config in, metrics + results.tsv row out
    ├── program.md     — spec: metric, commands, tunables, ideas, champion, change log
    ├── results.tsv    — run ledger (train.py appends; humans append only crash rows)
    ├── prepare.py     — one-time data/eval setup (optional; frozen during loops)
    ├── configs/       — one YAML per run, named after what changed (lr_3e5.yml)
    ├── logs/          — one log per run (.gitkeep so the dir exists before first run)
    ├── data/          — datasets / frozen eval set (gitignore if large)
    └── outputs/       — weights / heavy artifacts (gitignored)
```

If the project already has an `experiments/` tree with its own conventions (e.g. MLflow naming,
a CLAUDE.md champion table), follow those instead — they win over these defaults.

## Tracking

- `results.tsv` + `logs/` + `program.md` are always the source of truth.
- MLflow is optional: add it when the project already uses it or the user asks. See the MLflow
  section in `references/create-experiment.md`.

## Standing rules (both modes)

- Use `uv` for Python (`uv run`, `uv add`); never hand-edit dependency files.
- Never commit. At the end of a loop, propose commits grouped by round and wait for the user.
- Never modify `prepare.py` or eval data during a loop.
- One run at a time — no parallel runs (shared GPU/services make results noisy and crash-prone).
