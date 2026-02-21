"""Tests for candidate-side verification."""

from __future__ import annotations

from cegvr.candidate.types import CandidateOutput
from cegvr.candidate.verifier import verify_linear_candidate


SAT_PROBLEM = {
    "problem_id": "linear-sat",
    "task": "math",
    "variables": [{"name": "x", "domain": "int", "bounds": {"lower": 0, "upper": 5}}],
    "constraints": [
        {
            "constraint_id": "c1",
            "kind": "linear_ineq",
            "terms": [{"variable": "x", "coefficient": 1}],
            "relation": "=",
            "rhs": 2,
        }
    ],
    "ground_truth": "sat",
}


UNSAT_PROBLEM = {
    "problem_id": "linear-unsat",
    "task": "math",
    "variables": [{"name": "x", "domain": "int", "bounds": {"lower": 0, "upper": 5}}],
    "constraints": [
        {
            "constraint_id": "c1",
            "kind": "linear_ineq",
            "terms": [{"variable": "x", "coefficient": 1}],
            "relation": "=",
            "rhs": 2,
        },
        {
            "constraint_id": "c2",
            "kind": "linear_ineq",
            "terms": [{"variable": "x", "coefficient": 1}],
            "relation": "=",
            "rhs": 3,
        },
    ],
    "ground_truth": "unsat",
}


def test_sat_assignment_certifies() -> None:
    result = verify_linear_candidate(
        SAT_PROBLEM,
        CandidateOutput(status="sat", assignment={"x": 2}),
        timeout_ms=1000,
    )
    assert result.verified_outcome == "CERTIFIED_SAT"
    assert result.certified_assignment == {"x": 2}


def test_wrong_sat_assignment_returns_core_feedback() -> None:
    result = verify_linear_candidate(
        SAT_PROBLEM,
        CandidateOutput(status="sat", assignment={"x": 0}),
        timeout_ms=1000,
    )
    assert result.verified_outcome == "FAILED_CERTIFICATION"
    assert result.verifier_result == "unsat"
    assert result.unsat_core
    assert result.unsat_core[0].constraint_id == "c1"


def test_unsat_claim_certifies_on_unsat_problem() -> None:
    result = verify_linear_candidate(
        UNSAT_PROBLEM,
        CandidateOutput(status="unsat"),
        timeout_ms=1000,
    )
    assert result.verified_outcome == "CERTIFIED_UNSAT"
    assert len(result.unsat_core) >= 1


def test_false_unsat_claim_returns_witness() -> None:
    result = verify_linear_candidate(
        SAT_PROBLEM,
        CandidateOutput(status="unsat"),
        timeout_ms=1000,
    )
    assert result.verified_outcome == "FALSE_UNSAT_CLAIM"
    assert result.sat_witness is not None
    assert result.sat_witness["x"] == 2
