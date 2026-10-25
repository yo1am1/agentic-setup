# Create a project-development experiment

Create `experiments/dev_<repo>_<task>/` with:

```text
program.md
target.yml
train.py
results.tsv
configs/baseline.yml
logs/.gitkeep
artifacts/.gitkeep
patches/.gitkeep
```

`program.md` must name one primary metric, direction, threshold, fixed evidence,
hard gates, secondaries, isolation strategy, exact commands, ideas, and champion.
`target.yml` pins the repository path and baseline revision/state fingerprint.
`results.tsv` keeps `config` first, the primary metric second, `status`
second-to-last, and `description` last.

Scaffold with:

```bash
agent-env autoresearch new dev_<repo>_<task> \
  --repo /absolute/repository/path \
  --metric <metric> --direction higher \
  --acceptance '<threshold>' \
  --hard-gate '<gate>'
```

Run the baseline before proposing tunables. Use immutable YAML configs; do not
mutate the evaluator or fixed evidence during a loop.
