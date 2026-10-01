# <name> — experiment

<One sentence: what is being tested and what varies.>

## Metric

**Primary:** `<primary_metric>` — <higher|lower> is better.
**Secondary:** `<metric_b>` (diagnostic), `<cost_metric>` (cost).

<One sentence defining how the primary metric is computed and on which frozen eval set.>

## Setup

<Dependencies, services (e.g. Ollama at localhost:11434), API keys, GPU needs, data source.>

## Commands

```bash
uv run experiments/<name>/prepare.py        # once — <what it does>  (remove if no prepare.py)
PYTHONUNBUFFERED=1 uv run experiments/<name>/train.py --config experiments/<name>/configs/<config>.yml > experiments/<name>/logs/<config>.log 2>&1
```

## Read results

```bash
grep "config:\|<primary_metric>:\|<metric_b>:\|status:" experiments/<name>/logs/<config>.log
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
- `<config_name>`: <what changes> — <expected effect on primary metric>

## Champion results (as of last loop)

| config | <primary> | <secondary> | notes |
|--------|-----------|-------------|-------|
| — | — | — | not yet run |

Key findings:
- —

## Change log

Code changes made during loops (additive, default-off). Date — file — change — why — first config using it.

- —
