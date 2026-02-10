"""Build side-by-side comparison for linear dataset (baseline vs feedback)."""

from __future__ import annotations

import csv
from pathlib import Path


def load_table(path: Path) -> dict[str, float]:
    vals: dict[str, float] = {}
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            vals[row["metric"]] = float(row["value"])
    return vals


def main() -> None:
    base = Path("tables/linear/baseline_main_results.csv")
    feed = Path("tables/linear/main_results.csv")
    out = Path("tables/linear/compare.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    base_vals = load_table(base)
    feed_vals = load_table(feed)
    fields = ["variant", "certified_accuracy", "avg_iterations", "avg_latency_ms"]
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerow(
            {
                "variant": "baseline (1 round)",
                "certified_accuracy": f"{base_vals.get('certified_accuracy', 0):.3f}",
                "avg_iterations": f"{base_vals.get('avg_iterations', 0):.3f}",
                "avg_latency_ms": f"{base_vals.get('avg_latency_ms', 0):.1f}",
            }
        )
        w.writerow(
            {
                "variant": "feedback (3 rounds)",
                "certified_accuracy": f"{feed_vals.get('certified_accuracy', 0):.3f}",
                "avg_iterations": f"{feed_vals.get('avg_iterations', 0):.3f}",
                "avg_latency_ms": f"{feed_vals.get('avg_latency_ms', 0):.1f}",
            }
        )
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

