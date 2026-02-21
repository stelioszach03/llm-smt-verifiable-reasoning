"""Sanity checks for table generation utilities."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from cegvr.tables.main import (
    generate_ablation_table,
    generate_difficulty_breakdown_table,
    generate_main_table,
)


def write_sample_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "arm": "one_shot",
            "seed": 0,
            "problem_id": "p1",
            "task": "math",
            "ground_truth": "sat",
            "status": "certified",
            "certified": True,
            "predicted_status": "sat",
            "verified_outcome": "CERTIFIED_SAT",
            "iterations": 2,
            "latency_ms": 120,
            "solver_calls": 1,
            "llm_latency_ms": 10,
            "solver_latency_ms": 20,
            "total_tokens": 50,
            "config": {"use_grammar": True, "use_solver": True, "enable_repair": True},
            "per_round_candidates": 2,
            "max_rounds": 5,
            "timeout_ms": 2000,
            "problem_features": {"difficulty_bin": "easy"},
        },
        {
            "arm": "multi_generic_feedback",
            "seed": 0,
            "problem_id": "p2",
            "task": "scheduling",
            "ground_truth": "unsat",
            "status": "failed",
            "certified": False,
            "predicted_status": "unsat",
            "verified_outcome": "BUDGET_EXCEEDED",
            "iterations": 1,
            "latency_ms": 200,
            "solver_calls": 1,
            "llm_latency_ms": 20,
            "solver_latency_ms": 10,
            "total_tokens": 60,
            "config": {
                "use_grammar": False,
                "use_solver": False,
                "enable_repair": False,
            },
            "per_round_candidates": 1,
            "max_rounds": 1,
            "timeout_ms": 2000,
            "problem_features": {"difficulty_bin": "hard"},
        },
    ]
    output = run_dir / "seed_0.jsonl"
    output.write_text(
        "\n".join(json.dumps(record) for record in records), encoding="utf-8"
    )


def test_tables_contain_expected_columns(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    write_sample_run(runs_dir)

    tables_dir = tmp_path / "tables"
    generate_main_table(runs_dir, tables_dir / "main_results.csv")
    generate_ablation_table(runs_dir, tables_dir / "ablations.csv")
    generate_difficulty_breakdown_table(runs_dir, tables_dir / "difficulty_breakdown.csv")

    with (tables_dir / "main_results.csv").open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert {"arm", "verified_solve_rate", "latency_mean_ms"}.issubset(
        reader.fieldnames or []
    )
    assert rows, "Main table should contain data rows"

    with (tables_dir / "ablations.csv").open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert {
        "comparison",
        "success_mcnemar_p",
        "latency_wilcoxon_p",
    }.issubset(reader.fieldnames or [])
    assert rows == [], "Pairwise table can be empty when no compute-matched arm pairs exist"

    with (tables_dir / "difficulty_breakdown.csv").open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert {"arm", "difficulty_bin", "verified_solve_rate"}.issubset(
        reader.fieldnames or []
    )
    assert rows
