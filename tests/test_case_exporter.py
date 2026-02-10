"""Tests for the case study exporter."""

from __future__ import annotations

import json
from pathlib import Path

from cegvr.report.case_studies import export_case_studies


def write_sample_data(tmp_path: Path) -> tuple[Path, Path]:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    records = [
        {
            "problem_id": "p_sat",
            "task": "math",
            "status": "certified",
            "certified": True,
            "iterations": 1,
            "latency_ms": 100,
            "solver_calls": 1,
            "model": {"x": 2},
            "trace": {"problem_id": "p_sat"},
            "feedback": {},
        },
        {
            "problem_id": "p_unsat",
            "task": "math",
            "status": "failed",
            "certified": False,
            "iterations": 2,
            "latency_ms": 150,
            "solver_calls": 2,
            "feedback": {
                "issues": [{"type": "unsat_core", "unsat_core": ["c1", "c2"]}]
            },
        },
    ]
    (runs_dir / "seed_0.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records), encoding="utf-8"
    )

    problems_path = tmp_path / "problems.jsonl"
    problems = [
        {
            "problem_id": "p_sat",
            "task": "math",
            "variables": [],
            "constraints": [],
            "ground_truth": "sat",
        },
        {
            "problem_id": "p_unsat",
            "task": "math",
            "variables": [],
            "constraints": [],
            "ground_truth": "unsat",
        },
    ]
    problems_path.write_text(
        "\n".join(json.dumps(p) for p in problems), encoding="utf-8"
    )
    return runs_dir, problems_path


def test_case_study_export_contains_sections(tmp_path: Path) -> None:
    runs_dir, problems_path = write_sample_data(tmp_path)
    output = tmp_path / "case_studies.md"
    export_case_studies(
        run_dir=runs_dir, problems_path=problems_path, output_path=output, n=1
    )
    content = output.read_text(encoding="utf-8")
    assert "# Case Studies" in content
    assert "## Certified SAT Cases" in content
    assert "## UNSAT Cases" in content
    assert "Problem `p_sat`" in content
    assert "Problem `p_unsat`" in content
    assert "Unsat core" in content
