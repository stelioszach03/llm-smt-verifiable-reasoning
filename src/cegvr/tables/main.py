"""Table generation utilities for paper assets."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import List

from cegvr.eval.aggregate import aggregate_runs, load_run


def _collect_run_files(runs_dir: Path) -> List[Path]:
    return sorted(path for path in runs_dir.glob("seed_*.jsonl") if path.is_file())


def _summarize_main_metrics(run_files: List[Path]) -> List[dict]:
    summary = (
        aggregate_runs(run_files)
        if run_files
        else {
            "count": 0,
            "certified_accuracy": {"value": 0.0, "lower": 0.0, "upper": 0.0},
            "uncertified_accuracy": {
                "value": 0.0,
                "lower": 0.0,
                "upper": 0.0,
            },
            "avg_iterations": {"value": 0.0, "lower": 0.0, "upper": 0.0},
            "avg_latency_ms": {"value": 0.0, "lower": 0.0, "upper": 0.0},
            "per_task": {},
        }
    )

    def _count_row(metric: str, value: int) -> dict:
        return {"metric": metric, "value": value, "lower": value, "upper": value}

    rows = [
        {"metric": "certified_accuracy", **summary["certified_accuracy"]},
        {"metric": "uncertified_accuracy", **summary["uncertified_accuracy"]},
        {"metric": "avg_iterations", **summary["avg_iterations"]},
        {"metric": "avg_latency_ms", **summary["avg_latency_ms"]},
        _count_row("count", int(summary.get("count", 0))),
    ]

    for task, count in summary.get("per_task", {}).items():
        rows.append(_count_row(f"count_{task}", int(count)))

    return rows


def generate_main_table(runs_dir: Path | str, output_csv: Path | str) -> List[dict]:
    """Generate the main results table CSV and return the written rows."""

    runs_dir = Path(runs_dir)
    output_csv = Path(output_csv)
    run_files = _collect_run_files(runs_dir)
    rows = _summarize_main_metrics(run_files)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = ["metric", "value", "lower", "upper"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})

    return rows


def generate_ablation_table(runs_dir: Path | str, output_csv: Path | str) -> None:
    """Generate ablation table CSV summarising different flag combinations."""

    runs_dir = Path(runs_dir)
    output_csv = Path(output_csv)
    run_files = _collect_run_files(runs_dir)

    records: List[dict] = []
    for path in run_files:
        records.extend(load_run(path))

    grouped: dict[tuple[bool, bool, bool], List[dict]] = defaultdict(list)
    for record in records:
        config = record.get("config", {})
        key = (
            bool(config.get("use_grammar", True)),
            bool(config.get("use_solver", True)),
            bool(config.get("enable_repair", True)),
        )
        grouped[key].append(record)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "use_grammar",
        "use_solver",
        "enable_repair",
        "count",
        "certified_accuracy",
        "uncertified_accuracy",
        "avg_iterations",
        "avg_latency_ms",
    ]

    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for key, entries in sorted(grouped.items()):
            count = len(entries)
            if not count:
                continue
            certified_accuracy = (
                sum(1.0 if entry.get("certified") else 0.0 for entry in entries) / count
            )
            uncertified_accuracy = (
                sum(
                    1.0 if entry.get("uncertified_correct") else 0.0
                    for entry in entries
                )
                / count
            )
            avg_iterations = (
                sum(entry.get("iterations", 0) or 0 for entry in entries) / count
            )
            avg_latency = (
                sum(entry.get("latency_ms", 0.0) or 0.0 for entry in entries) / count
            )
            writer.writerow(
                {
                    "use_grammar": key[0],
                    "use_solver": key[1],
                    "enable_repair": key[2],
                    "count": count,
                    "certified_accuracy": round(certified_accuracy, 4),
                    "uncertified_accuracy": round(uncertified_accuracy, 4),
                    "avg_iterations": round(avg_iterations, 2),
                    "avg_latency_ms": round(avg_latency, 2),
                }
            )


def generate_main_table_tex(
    output_tex: Path | str,
    *,
    csv_reference: str = "tables/main_results.csv",
) -> None:
    """Write a LaTeX snippet that renders the main results CSV via pgfplotstable."""

    output_tex = Path(output_tex)
    output_tex.parent.mkdir(parents=True, exist_ok=True)

    latex = (
        "% LaTeX snippet generated by CEGVR make-tables\n"
        "% Requires \\usepackage{pgfplotstable}\n\n"
        "\\pgfplotstableset{\n"
        "  every head row/.style={before row=\\toprule, after row=\\midrule},\n"
        "  every last row/.style={after row=\\bottomrule},\n"
        "}\n\n"
        "\\pgfplotstabletypeset[\n"
        "  col sep=comma,\n"
        "  header=has colnames,\n"
        "  trim cells=true,\n"
        "  columns/metric/.style={string type,string replace*={_}{\\_}},\n"
        "  columns/value/.style={fixed, precision=3},\n"
        "  columns/lower/.style={fixed, precision=3},\n"
        "  columns/upper/.style={fixed, precision=3},\n"
        f"]{{{csv_reference}}}\n"
    )

    output_tex.write_text(latex, encoding="utf-8")


__all__ = [
    "generate_main_table",
    "generate_ablation_table",
    "generate_main_table_tex",
]
