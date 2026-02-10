from __future__ import annotations

import csv
from pathlib import Path
import matplotlib.pyplot as plt


def load_table(path: Path) -> dict[str, float]:
    vals: dict[str, float] = {}
    with path.open() as f:
        rd = csv.DictReader(f)
        for row in rd:
            vals[row["metric"]] = float(row["value"])
    return vals


def main() -> None:
    base = Path("tables/linear/baseline_main_results.csv")
    feed = Path("tables/linear/main_results.csv")
    out = Path("examples/paper_assets/figures_linear/compare.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    b = load_table(base)
    f = load_table(feed)
    metrics = ["certified_accuracy", "avg_latency_ms"]
    labels = ["Certified Acc.", "Avg Latency (ms)"]
    bvals = [b.get(m, 0.0) for m in metrics]
    fvals = [f.get(m, 0.0) for m in metrics]
    x = range(len(metrics))
    w = 0.35
    fig, ax = plt.subplots(figsize=(5, 3))
    ax.bar([i - w / 2 for i in x], bvals, width=w, label="Baseline")
    ax.bar([i + w / 2 for i in x], fvals, width=w, label="Feedback")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylim(0, max(bvals + fvals) * 1.2 if max(bvals + fvals) > 0 else 1)
    ax.legend(loc="best")
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

