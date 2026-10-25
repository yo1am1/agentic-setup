# Create an experiment

Scaffold `experiments/<name>/` from a description, run the baseline, register it in the index.

Paths below are relative to the project root. `<skill>` = the directory holding this skill's
`SKILL.md`.

## 0. Pin down the spec

From the user's description, extract:

- **Name** — short `snake_case`, descriptive: `load_time_nginx`, not `exp1`.
- **Primary metric + direction** — exactly one, used for champion gating.
- **Secondary metrics** — any number, diagnostics only (a cost metric such as time, memory or
  tokens is usually worth having).
- **Eval data** — where it comes from, how it's frozen, whether a `prepare.py` is needed.
- **Tunables** — the knobs the loop will turn, with baseline values.
- **Requirements** — GPU, local services (Ollama, DBs), API keys, network.
- **MLflow** — use it only if the project already has MLflow or the user asks.

If the primary metric, its direction, or the eval data is unclear, ask before writing files —
those three define whether a run "improved", and a wrong guess invalidates every later run.
Everything else can take a sensible default and be listed in the final report.

## 1. Create files

```
experiments/<name>/
├── train.py           ← <skill>/templates/train.py
├── program.md         ← <skill>/templates/program.md
├── results.tsv        ← header row only
├── prepare.py         ← only if data must be downloaded/built
├── configs/baseline.yml ← <skill>/templates/baseline.yml
└── logs/.gitkeep
```

`logs/` must exist before the first run: the run command redirects into `logs/<config>.log`,
and a missing directory makes the shell redirect fail before `train.py` even starts.

Add `pyyaml` (and `mlflow` if used, plus whatever the experiment needs) with `uv add`.
Add large `data/` files and `outputs/` to `.gitignore`.

## 2. `train.py` contract

Start from `<skill>/templates/train.py`. It already implements:

- `--config <yaml>`; config name = YAML file stem.
- `HIGHER_IS_BETTER` flag — flip to `False` for loss, latency, bpb, error rate.
- `_read_champion()` — best primary value from column 1 of `results.tsv`, skipping crash rows;
  seeds with ±inf so the first run always keeps.
- `status = keep` if primary ties or beats the champion, else `discard`.
- `_append_result()` — appends one row after the run finishes.
- Prints `config:`, `<primary>:`, secondaries, and `status: ... (champion was X)`.

Fill in: metric names, the actual run logic, the header columns.

Keep cheap, deterministic setup (load config, load frozen data) before the run block and the
expensive/fragile work inside it. The row is appended only after a successful run, so a crash
writes nothing — the loop then appends a `crash` row by hand.

Determinism matters: fix seeds and splits so the same config yields the same score. A noisy
metric makes keep/discard decisions meaningless.

### `results.tsv` column order

| position | column |
|---|---|
| first | `config` |
| second (index 1) | primary metric — `_read_champion()` reads this |
| middle | secondary metrics, then config params, any order |
| second-to-last | `status` (`keep` / `discard` / `crash`) |
| last | `description` (from the YAML) |

Values tab-separated; format floats consistently (`.4f`).

### Optional: MLflow

When MLflow is used, wrap the run in a tracked block and log params/metrics:

```python
import mlflow

REPO_ROOT = Path(__file__).resolve().parents[2]              # experiments/<name>/train.py → root
TRACKING_URI = "sqlite:///" + str(REPO_ROOT / "mlflow.db")   # one DB at project root
EXPERIMENT = "<project>-<name-with-dashes>"                  # never rename after the first run

mlflow.set_tracking_uri(TRACKING_URI)
mlflow.set_experiment(EXPERIMENT)
with mlflow.start_run(run_name=cfg_name):
    mlflow.log_params({k: v for k, v in cfg.items() if k != "description"})
    ...  # run
    mlflow.log_metrics({"<primary>": primary, "<secondary>": secondary})
    mlflow.log_artifact(args.config)
```

Keep the experiment name stable forever: renaming breaks run history and model-registry links.
If the project already has a naming convention, use it. The UI is
`uv run mlflow ui --backend-store-uri sqlite:///mlflow.db`.

## 3. `program.md`

Fill `<skill>/templates/program.md` completely. The run loop reads it as its only spec, so it
must contain everything the loop needs: metric + direction, exact run and grep commands, the
results.tsv columns, every YAML tunable with a comment, 5–10 ordered **Ideas to explore**
(each: config name — what changes — expected effect), and requirements (GPU, services).

## 4. Baseline run

```bash
uv run experiments/<name>/prepare.py        # if it exists
PYTHONUNBUFFERED=1 uv run experiments/<name>/train.py --config experiments/<name>/configs/baseline.yml > experiments/<name>/logs/baseline.log 2>&1
grep "config:\|<primary>:\|status:" experiments/<name>/logs/baseline.log
```

`PYTHONUNBUFFERED=1` makes the log stream line by line, so progress and crash tracebacks are
visible while the run is going.

Fix anything that breaks. Update the Champion table in `program.md` with the baseline result.

## 5. Register in the index

Update `experiments/README.md` (create it from `<skill>/templates/experiments_readme.md` if
missing): one layout line and one champion-table row. If the experiment reads data from another
experiment, add it to the data-sharing table. If the project instead keeps this index in
`CLAUDE.md`/`AGENTS.md`, update it there.

## Verification checklist

- [ ] `logs/` exists with `.gitkeep`
- [ ] `prepare.py` runs cleanly (if present)
- [ ] baseline runs end to end and prints `status:`
- [ ] `results.tsv` has exactly one data row; header order matches `_append_result`
- [ ] `HIGHER_IS_BETTER` matches the metric direction
- [ ] same config run twice gives the same primary metric (or the noise is documented in program.md)
- [ ] MLflow run landed in the project-root `mlflow.db` (if MLflow is used)
- [ ] `program.md` complete; `experiments/README.md` updated
- [ ] nothing committed — suggest a commit message (`feat(<name>): scaffold experiment + baseline`) and let the user decide
