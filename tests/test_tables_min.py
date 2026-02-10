"""Sanity checks for table generation utilities."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from cegvr.tables.main import generate_ablation_table, generate_main_table


def write_sample_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "seed": 0,
            "problem_id": "p1",
            "task": "math",
            "status": "certified",
            "certified": True,
            "uncertified_correct": False,
            "iterations": 2,
            "latency_ms": 120,
            "solver_calls": 1,
            "config": {"use_grammar": True, "use_solver": True, "enable_repair": True},
            "budget": 2,
            "max_rounds": 5,
            "timeout_ms": 2000,
        },
        {
            "seed": 0,
            "problem_id": "p2",
            "task": "scheduling",
            "status": "failed",
            "certified": False,
            "uncertified_correct": True,
            "iterations": 1,
            "latency_ms": 200,
            "solver_calls": 1,
            "config": {
                "use_grammar": False,
                "use_solver": False,
                "enable_repair": False,
            },
            "budget": 1,
            "max_rounds": 1,
            "timeout_ms": 2000,
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

    with (tables_dir / "main_results.csv").open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert {"metric", "value", "lower", "upper"}.issubset(reader.fieldnames or [])
    assert rows, "Main table should contain data rows"

    with (tables_dir / "ablations.csv").open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert {
        "use_grammar",
        "use_solver",
        "enable_repair",
        "certified_accuracy",
    }.issubset(reader.fieldnames or [])
    assert rows, "Ablation table should contain data rows"
