"""Tests for dataset loading and adapter helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from cegvr.data.adapters import batch_normalize, normalize_problem
from cegvr.data.loader import (
    VALID_TASKS,
    filter_by_task,
    load_jsonl_problems,
    summarize_by_task,
)

DATASET_PATH = Path("data/toy/problems.jsonl")


def test_load_jsonl_problems_counts_items() -> None:
    problems = load_jsonl_problems(DATASET_PATH)
    total = len(problems)
    summary = summarize_by_task(problems)
    assert sum(summary.values()) == total
    assert total > 0
    for task in VALID_TASKS:
        assert summary[task] > 0


def test_filter_by_task_returns_expected_subset() -> None:
    problems = load_jsonl_problems(DATASET_PATH)
    math_problems = filter_by_task(problems, "math")
    assert all(problem["task"] == "math" for problem in math_problems)
    with pytest.raises(ValueError):
        filter_by_task(problems, "invalid")


def test_normalize_problem_includes_metadata() -> None:
    raw = {
        "problem_id": "demo",
        "task": "math",
        "variables": [
            {"name": "x", "domain": "int", "bounds": {"lower": 0, "upper": 1}}
        ],
        "constraints": [],
        "objective": None,
        "ground_truth": "sat",
    }
    normalized = normalize_problem(raw)
    assert normalized["metadata"]["ground_truth"] == "sat"
    batch = batch_normalize([raw, raw])
    assert len(batch) == 2
