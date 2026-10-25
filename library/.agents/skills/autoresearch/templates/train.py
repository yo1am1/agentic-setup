"""<One-line description of what this experiment measures>."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

RESULTS_PATH = Path(__file__).parent / "results.tsv"
DATA_DIR = Path(__file__).parent / "data"
# Cross-experiment data (if needed): Path(__file__).parent.parent / "<other_experiment>" / "data"

PRIMARY = "<primary_metric>"
HIGHER_IS_BETTER = True  # False for loss / latency / bpb / error rate

# Order must match the row written in _append_result.
HEADER = [
    "config",
    PRIMARY,
    "<secondary_metric>",
    "<param_a>",
    "status",
    "description",
]


def _read_champion() -> float:
    """Best primary metric so far (col 1 of results.tsv).

    Seeds with the worst possible value so the first run always keeps.
    Crash rows have a non-numeric metric cell and are skipped.
    """
    seed = float("-inf") if HIGHER_IS_BETTER else float("inf")
    if not RESULTS_PATH.exists():
        return seed
    best = seed
    rows = [line for line in RESULTS_PATH.read_text().splitlines() if line.strip()][1:]
    for row in rows:
        cells = row.split("\t")
        if len(cells) < 2:
            continue
        try:
            value = float(cells[1])
        except ValueError:
            continue
        best = max(best, value) if HIGHER_IS_BETTER else min(best, value)
    return best


def _append_result(cells: list[str]) -> None:
    if not RESULTS_PATH.exists():
        RESULTS_PATH.write_text("\t".join(HEADER) + "\n")
    with RESULTS_PATH.open("a") as f:
        f.write("\t".join(cells) + "\n")


def run_experiment(cfg: dict) -> dict[str, float]:
    """Run one configuration and return {metric_name: value}. Replace with real logic.

    Keep it deterministic: fixed seeds, fixed splits, frozen eval data from DATA_DIR.
    """
    raise NotImplementedError


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text()) or {}
    cfg_name = Path(args.config).stem
    description = str(cfg.get("description", ""))

    # Cheap, deterministic setup above; expensive/fragile work inside run_experiment.
    # A crash here writes no row; the loop appends a crash row by hand.
    metrics = run_experiment(cfg)
    primary = metrics[PRIMARY]

    champion = _read_champion()
    improved = primary >= champion if HIGHER_IS_BETTER else primary <= champion
    status = "keep" if improved else "discard"

    _append_result(
        [
            cfg_name,
            f"{primary:.4f}",
            f"{metrics['<secondary_metric>']:.4f}",
            str(cfg.get("<param_a>")),
            status,
            description,
        ]
    )

    # The loop greps these lines; keep the "name:" format.
    print("---")
    print(f"config: {cfg_name}")
    for name, value in metrics.items():
        print(f"{name}: {value:.4f}")
    print(f"status: {status}  (champion was {champion:.4f})")
    print(f"description: {description}")


if __name__ == "__main__":
    main()
