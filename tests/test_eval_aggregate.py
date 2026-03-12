"""Tests for evaluation aggregation utilities."""

from __future__ import annotations

import json
from pathlib import Path

from cegvr.eval.aggregate import aggregate_runs, load_run

FIXTURE = Path("tests/fixtures/sample_runs.jsonl")


def test_load_run_reads_jsonl() -> None:
    records = load_run(FIXTURE)
    assert len(records) == 3
    assert records[0]["certified"] is True


def test_aggregate_runs_reports_metrics() -> None:
    summary = aggregate_runs([FIXTURE])
    assert summary["count"] == 3
    assert "value" in summary["overall"]["verified_solve_rate"]
    assert "one_shot" in summary["per_arm"]
    assert summary["per_task"]["math"] == 1


def test_aggregate_runs_tracks_cd_vgs_and_difficulty_breakdown(
    tmp_path: Path,
) -> None:
    run_file = tmp_path / "seed_0.jsonl"
    records = [
        {
            "arm": "multi_no_feedback",
            "seed": 0,
            "problem_id": "p1",
            "task": "math",
            "ground_truth": "sat",
            "predicted_status": "sat",
            "verified_outcome": "BUDGET_EXCEEDED",
            "latency_ms": 3.0,
            "solver_calls": 4,
            "llm_latency_ms": 2.0,
            "solver_latency_ms": 0.5,
            "iterations": 4,
            "total_tokens": 40,
            "problem_features": {"difficulty_bin": "hard"},
        },
        {
            "arm": "multi_generic_feedback",
            "seed": 0,
            "problem_id": "p1",
            "task": "math",
            "ground_truth": "sat",
            "predicted_status": "sat",
            "verified_outcome": "BUDGET_EXCEEDED",
            "latency_ms": 4.0,
            "solver_calls": 4,
            "llm_latency_ms": 3.0,
            "solver_latency_ms": 0.5,
            "iterations": 4,
            "total_tokens": 45,
            "problem_features": {"difficulty_bin": "hard"},
        },
        {
            "arm": "multi_unsat_core_feedback",
            "seed": 0,
            "problem_id": "p1",
            "task": "math",
            "ground_truth": "sat",
            "predicted_status": "sat",
            "verified_outcome": "CERTIFIED_SAT",
            "latency_ms": 2.0,
            "solver_calls": 2,
            "llm_latency_ms": 1.5,
            "solver_latency_ms": 0.4,
            "iterations": 2,
            "total_tokens": 30,
            "problem_features": {"difficulty_bin": "hard"},
        },
        {
            "arm": "cd_vgs_core_rank",
            "seed": 0,
            "problem_id": "p1",
            "task": "math",
            "ground_truth": "sat",
            "predicted_status": "sat",
            "verified_outcome": "CERTIFIED_SAT",
            "latency_ms": 1.5,
            "solver_calls": 1,
            "llm_latency_ms": 1.0,
            "solver_latency_ms": 0.2,
            "iterations": 1,
            "total_tokens": 20,
            "problem_features": {"difficulty_bin": "hard"},
        },
    ]
    run_file.write_text(
        "\n".join(json.dumps(record) for record in records), encoding="utf-8"
    )

    summary = aggregate_runs([run_file])

    assert "cd_vgs_core_rank" in summary["per_arm"]
    assert "hard" in summary["per_arm_per_difficulty"]["cd_vgs_core_rank"]
    assert "cd_vgs_core_rank__vs__multi_unsat_core_feedback" in summary["comparisons"]
