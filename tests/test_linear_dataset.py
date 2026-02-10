"""Validation tests for the generated linear dataset."""

from __future__ import annotations

from pathlib import Path

from cegvr.data.loader import iter_jsonl_problems
from cegvr.engine.repair import repair_until_certified
from cegvr.generation.provider import StubGenerator


DATA_PATH = Path("data/linear/problems.jsonl")


def _find_examples(status: str, count: int) -> list[dict]:
    results: list[dict] = []
    for problem in iter_jsonl_problems(DATA_PATH):
        if problem.get("ground_truth") == status:
            results.append(problem)
        if len(results) == count:
            break
    return results


def test_linear_dataset_satisfiable_examples_certify() -> None:
    examples = _find_examples("sat", count=3)
    assert examples, "Expected at least one satisfiable example"

    generator = StubGenerator(seed=0)

    for problem in examples:
        outcome = repair_until_certified(
            problem,
            generator,
            max_rounds=1,
            per_round_budget=1,
            timeout_ms=1000,
        )
        assert outcome["status"] == "certified", problem["problem_id"]


def test_linear_dataset_unsatisfiable_examples_fail() -> None:
    examples = _find_examples("unsat", count=3)
    assert examples, "Expected at least one unsatisfiable example"

    generator = StubGenerator(seed=1)

    for problem in examples:
        outcome = repair_until_certified(
            problem,
            generator,
            max_rounds=1,
            per_round_budget=1,
            timeout_ms=1000,
        )
        assert outcome["status"] == "failed", problem["problem_id"]
