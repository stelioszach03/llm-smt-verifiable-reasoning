"""Tests for evaluation aggregation utilities."""

from __future__ import annotations

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
    assert "value" in summary["certified_accuracy"]
    assert summary["per_task"]["math"] == 1
