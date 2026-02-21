"""Table generation utilities for paper assets."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import List

from cegvr.eval.aggregate import aggregate_runs

_ARM_ORDER = {
    "one_shot": 0,
    "multi_no_feedback": 1,
    "multi_generic_feedback": 2,
    "multi_unsat_core_feedback": 3,
    "cd_vgs_core_rank": 4,
}


def _collect_run_files(runs_dir: Path) -> List[Path]:
    return sorted(path for path in runs_dir.rglob("seed_*.jsonl") if path.is_file())


def generate_main_table(runs_dir: Path | str, output_csv: Path | str) -> List[dict]:
    """Generate the main arm-by-arm results table CSV."""

    runs_dir = Path(runs_dir)
    output_csv = Path(output_csv)
    summary = aggregate_runs(_collect_run_files(runs_dir))

    rows: List[dict] = []
    for arm_name, payload in sorted(
        summary.get("per_arm", {}).items(),
        key=lambda item: (_ARM_ORDER.get(item[0], 999), item[0]),
    ):
        rows.append(
            {
                "arm": arm_name,
                "count": payload.get("count", 0),
                "verified_solve_rate": payload["verified_solve_rate"]["value"],
                "verified_solve_rate_lower": payload["verified_solve_rate"]["lower"],
                "verified_solve_rate_upper": payload["verified_solve_rate"]["upper"],
                "sat_certification_rate": payload["sat_certification_rate"]["value"],
                "unsat_precision": payload["unsat_precision"]["value"],
                "unsat_recall": payload["unsat_recall"]["value"],
                "solver_calls_per_certified_solve": payload[
                    "solver_calls_per_certified_solve"
                ]["value"],
                "latency_mean_ms": payload["latency_mean_ms"]["value"],
                "latency_p95_ms": payload["latency_p95_ms"]["value"],
                "repair_gain_vs_one_shot": payload.get(
                    "repair_gain_vs_one_shot", {"value": 0.0}
                )["value"],
            }
        )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "arm",
            "count",
            "verified_solve_rate",
            "verified_solve_rate_lower",
            "verified_solve_rate_upper",
            "sat_certification_rate",
            "unsat_precision",
            "unsat_recall",
            "solver_calls_per_certified_solve",
            "latency_mean_ms",
            "latency_p95_ms",
            "repair_gain_vs_one_shot",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    return rows


def generate_difficulty_breakdown_table(
    runs_dir: Path | str, output_csv: Path | str
) -> List[dict]:
    """Generate a difficulty-bin breakdown CSV grouped by arm."""

    runs_dir = Path(runs_dir)
    output_csv = Path(output_csv)
    summary = aggregate_runs(_collect_run_files(runs_dir))

    rows: List[dict] = []
    for arm_name, by_difficulty in sorted(
        summary.get("per_arm_per_difficulty", {}).items(),
        key=lambda item: (_ARM_ORDER.get(item[0], 999), item[0]),
    ):
        for difficulty, payload in sorted(by_difficulty.items()):
            rows.append(
                {
                    "arm": arm_name,
                    "difficulty_bin": difficulty,
                    "count": payload.get("count", 0),
                    "verified_solve_rate": payload["verified_solve_rate"]["value"],
                    "sat_certification_rate": payload["sat_certification_rate"][
                        "value"
                    ],
                    "solver_calls_per_certified_solve": payload[
                        "solver_calls_per_certified_solve"
                    ]["value"],
                    "latency_mean_ms": payload["latency_mean_ms"]["value"],
                }
            )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "arm",
            "difficulty_bin",
            "count",
            "verified_solve_rate",
            "sat_certification_rate",
            "solver_calls_per_certified_solve",
            "latency_mean_ms",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    return rows


def generate_ablation_table(runs_dir: Path | str, output_csv: Path | str) -> None:
    """Generate the paired-comparison statistics table CSV."""

    runs_dir = Path(runs_dir)
    output_csv = Path(output_csv)
    summary = aggregate_runs(_collect_run_files(runs_dir))
    comparisons = summary.get("comparisons", {})

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "comparison",
        "n_pairs",
        "success_mcnemar_p",
        "success_mcnemar_p_holm",
        "latency_wilcoxon_p",
        "solver_calls_wilcoxon_p",
    ]
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for comparison, payload in sorted(comparisons.items()):
            writer.writerow(
                {
                    "comparison": comparison,
                    "n_pairs": payload.get("n_pairs", 0),
                    "success_mcnemar_p": payload.get("success_mcnemar_p", 1.0),
                    "success_mcnemar_p_holm": payload.get(
                        "success_mcnemar_p_holm", 1.0
                    ),
                    "latency_wilcoxon_p": payload.get("latency_wilcoxon_p", 1.0),
                    "solver_calls_wilcoxon_p": payload.get(
                        "solver_calls_wilcoxon_p", 1.0
                    ),
                }
            )


def generate_main_table_tex(
    output_tex: Path | str,
    *,
    csv_reference: str = "tables/main_results.csv",
) -> None:
    """Write a LaTeX snippet rendering the arm-level CSV via pgfplotstable."""

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
        "  columns/arm/.style={string type,string replace*={_}{\\_}},\n"
        "  columns/count/.style={fixed, precision=0},\n"
        "  columns/verified_solve_rate/.style={fixed, precision=3},\n"
        "  columns/sat_certification_rate/.style={fixed, precision=3},\n"
        "  columns/unsat_precision/.style={fixed, precision=3},\n"
        "  columns/unsat_recall/.style={fixed, precision=3},\n"
        "  columns/solver_calls_per_certified_solve/.style={fixed, precision=2},\n"
        "  columns/latency_mean_ms/.style={fixed, precision=1},\n"
        "  columns/latency_p95_ms/.style={fixed, precision=1},\n"
        f"]{{{csv_reference}}}\n"
    )

    output_tex.write_text(latex, encoding="utf-8")


__all__ = [
    "generate_main_table",
    "generate_difficulty_breakdown_table",
    "generate_ablation_table",
    "generate_main_table_tex",
]
