# Create Experiment

Scaffold a new experiment in this repo from a description.
Experiments can cover anything measurable: retrieval pipelines, prompt tuning,
model training, API latency, cache efficiency, security red-teaming, site load time, etc.

Requirements:
- One **primary metric** for champion gating (did this run improve over the last best?)
- Any number of **secondary metrics** tracked in MLflow and results.tsv for diagnostics

## Usage

```
@create-experiment.md <experiment description>
```

Examples:
```
@create-experiment.md Compare chunking strategies for RAG on SQuAD. Primary metric: retrieval_recall_at_10 (higher better). Secondary: n_chunks.
@create-experiment.md Tune Nginx config for homepage load time. Primary metric: p95_latency_ms (lower better). Secondary: p50_latency_ms, error_rate.
@create-experiment.md Red-team a customer-support system prompt. Primary metric: defense_score (higher better). Secondary: bypasses_found, prompt_chars.
```

---

## Step-by-step

1. **Choose a name** — short, `snake_case`, descriptive. `load_time_nginx` not `exp1`.
2. **Identify metrics** — one primary (for champion gating), any number of secondaries.
3. **Create the experiment folder** with all standard files (see below).
4. **Run the baseline config** to verify it works end-to-end.
5. **Update `CLAUDE.md`** — add to repo layout + champion table.

---

## Required file structure

All experiments live under `experiments/`.

```
experiments/<name>/
├── train.py           # main script — accepts --config, measures metrics, writes results.tsv
├── program.md         # experiment spec (use template below)
├── results.tsv        # header row only (train.py appends data rows)
├── prepare.py         # one-time setup — only if needed (download data, build index, etc.)
├── configs/
│   └── baseline.yml   # first config to run
└── logs/              # run output lands here; add an empty .gitkeep so the dir survives a clone
```

The run command redirects into `logs/<config>.log`, so `logs/` **must exist before the first run** — `mkdir -p` it and drop a `.gitkeep` in. A missing `logs/` makes the shell redirect fail before train.py even starts.

---

## `train.py` pattern

```python
"""One-line description."""
from __future__ import annotations
import argparse
from pathlib import Path
import mlflow
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]   # experiments/<name>/train.py → repo root
RESULTS_PATH = Path(__file__).parent / "results.tsv"
TRACKING_URI = "sqlite:///" + str(REPO_ROOT / "mlflow.db")   # always repo-root mlflow.db
EXPERIMENT = "autoresearch-<name>"   # CONVENTION: "autoresearch-" + folder name, dashes not underscores.
                                     # e.g. folder random_forest → "autoresearch-random-forest".
                                     # NEVER change this after the first run — breaks model registry linkage.
# Cross-experiment data (if needed): Path(__file__).parent.parent / "<other_experiment>" / "data"


HIGHER_IS_BETTER = True   # flip to False for metrics where lower wins (loss, latency, bpb)


def _read_champion() -> float:
    """Best PRIMARY metric seen so far, read from col 1 of results.tsv.
    Returns the worst-possible seed when no rows exist yet, so the first run always keeps."""
    seed = float("-inf") if HIGHER_IS_BETTER else float("inf")
    if not RESULTS_PATH.exists():
        return seed
    best = seed
    lines = [l for l in RESULTS_PATH.read_text().splitlines() if l.strip()][1:]
    for line in lines:
        parts = line.split("\t")
        if len(parts) >= 2:
            try:
                val = float(parts[1])   # col 1 = primary metric
            except ValueError:
                continue   # skip crash rows (non-numeric metric cell)
            best = max(best, val) if HIGHER_IS_BETTER else min(best, val)
    return best


def _append_result(config: str, primary: float, secondary_a: float, ..., status: str, description: str) -> None:
    header = "config\t<primary_metric>\t<secondary_a>\t...\t<config_params>\tstatus\tdescription"
    if not RESULTS_PATH.exists():
        RESULTS_PATH.write_text(header + "\n")
    with RESULTS_PATH.open("a") as f:
        f.write(f"{config}\t{primary:.4f}\t{secondary_a:.4f}\t...\t{status}\t{description}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    cfg.setdefault("config", Path(args.config).stem)

    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT)

    with mlflow.start_run(run_name=cfg["config"]):
        mlflow.log_params({k: v for k, v in cfg.items() if k != "description"})

        # --- run the experiment ---
        primary_metric = 0.0
        secondary_metric = 0.0

        mlflow.log_metric("<primary_metric>", primary_metric)
        mlflow.log_metric("<secondary_metric>", secondary_metric)

    champion = _read_champion()
    improved = primary_metric >= champion if HIGHER_IS_BETTER else primary_metric <= champion
    status = "keep" if improved else "discard"
    _append_result(cfg["config"], primary_metric, secondary_metric, ..., status, cfg.get("description", ""))

    # Always print these — autoresearch-start.md reads them
    print(f"config: {cfg['config']}")
    print(f"<primary_metric>: {primary_metric:.4f}")
    print(f"<secondary_metric>: {secondary_metric:.4f}")
    print(f"status: {status}  (champion was {champion:.4f})")


if __name__ == "__main__":
    main()
```

### Column rules for `results.tsv`

- `config` — always **first**
- **Primary metric** — always **second** (index 1) — `_read_champion()` reads this column
- Secondary metrics and config params — middle columns, any order
- `status` — always **second-to-last** (`keep` / `discard` / `crash`)
- `description` — always **last**

### Output rules

- Print `config:`, `<primary_metric>:`, `status:` to stdout — the loop reads these
- Prefix with `PYTHONUNBUFFERED=1` when redirecting to a log file
- `_append_result` runs **after** the `mlflow.start_run` block, so a crash mid-run writes **no** row to results.tsv (and the loop appends a `crash` row by hand). Keep cheap, deterministic setup before the run block and the expensive/fragile work inside it.

---

## `program.md` template

```markdown
# <name> — experiment

<One sentence: what is being tested and what varies.>

## Metric

**Primary:** `<metric_name>` — higher/lower is better.
**Secondary:** `<metric_b>` (diagnostic), `<metric_c>` (diagnostic).

<One sentence defining what the primary metric measures, if not self-evident.>

## Setup

<What the experiment needs: dependencies, services, credentials, data sources.>

## Commands

```bash
uv run experiments/<name>/prepare.py                    # once — <what it does> (remove if no prepare.py)
PYTHONUNBUFFERED=1 uv run experiments/<name>/train.py --config experiments/<name>/configs/<config>.yml > experiments/<name>/logs/<config>.log 2>&1
```

## Read results

```bash
grep "<primary_metric>\|<secondary_metric>\|status:\|config:" experiments/<name>/logs/<config>.log
```

## results.tsv columns

```
config  <primary>  <secondary>  [params]  status  description
```

## YAML tunables

```yaml
key: default_value   # what this controls
description: "short note"
```

## Ideas to explore

- `baseline`: starting point
- `config_name`: <what changes> — <expected effect on primary metric>

## Champion results (as of last loop)

| config | <primary> | <secondary> | notes |
|--------|-----------|-------------|-------|
| — | — | — | not yet run |
```

---

## `baseline.yml` template

```yaml
# First config. Document every key with a comment.
key: value      # what this controls
description: "baseline — <brief description>"
```

---

## `CLAUDE.md` updates

After creating files:

1. **Repo layout (`experiments/` table)** — one line:
   ```
   <name>/   <One sentence>. Metric: <primary> (<direction>).
   ```

2. **Champion table** — one row:
   ```
   | <name> | <primary_metric> | — | — |
   ```

3. **Cross-experiment data sharing** — if reusing data from another experiment, document it.

---

## Verification checklist

- [ ] `logs/` exists with a `.gitkeep` (redirect target must exist before the run)
- [ ] `uv run experiments/<name>/prepare.py` runs without error (if it exists)
- [ ] `uv run experiments/<name>/train.py --config experiments/<name>/configs/baseline.yml` runs end-to-end and prints `status:`
- [ ] `results.tsv` has exactly one data row after the baseline run, and its header column order matches `_append_result`
- [ ] MLflow experiment is named `autoresearch-<name>` (dashes) — matches the repo convention, not a bare folder name
- [ ] MLflow run appears in repo-root `mlflow.db` (not a stray `experiments/mlflow.db`)
- [ ] `HIGHER_IS_BETTER` matches the metric direction (loss/latency/bpb → `False`)
- [ ] `CLAUDE.md` updated (repo layout + champion table; cross-experiment data sharing if any)
