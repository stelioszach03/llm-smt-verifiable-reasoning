"""Validation tests for the generated linear dataset."""

from __future__ import annotations

from pathlib import Path

from cegvr.candidate.types import CandidateOutput
from cegvr.candidate.verifier import verify_linear_candidate
from cegvr.data.loader import iter_jsonl_problems


DATA_PATH = Path("data/linear/problems.jsonl")


def _find_examples(status: str, count: int) -> list[dict]:
    results: list[dict] = []
    for problem in iter_jsonl_problems(DATA_PATH):
        if problem.get("ground_truth") == status:
            results.append(problem)
        if len(results) == count:
            break
    return results


def test_linear_dataset_satisfiable_examples_are_solver_sat() -> None:
    examples = _find_examples("sat", count=3)
    assert examples, "Expected at least one satisfiable example"

    for problem in examples:
        outcome = verify_linear_candidate(
            problem,
            CandidateOutput(status="unsat"),
            timeout_ms=1000,
        )
        assert outcome.verified_outcome == "FALSE_UNSAT_CLAIM", problem["problem_id"]


def test_linear_dataset_unsatisfiable_examples_are_solver_unsat() -> None:
    examples = _find_examples("unsat", count=3)
    assert examples, "Expected at least one unsatisfiable example"

    for problem in examples:
        outcome = verify_linear_candidate(
            problem,
            CandidateOutput(status="unsat"),
            timeout_ms=1000,
        )
        assert outcome.verified_outcome == "CERTIFIED_UNSAT", problem["problem_id"]
