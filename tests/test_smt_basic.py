"""Basic SMT encoding regression tests."""

from __future__ import annotations

from cegvr.grammar.types import Trace
from cegvr.smt.runner import check_trace


def build_trace(payload: dict) -> Trace:
    return Trace.model_validate(payload)


def test_linear_system_satisfiable() -> None:
    trace = build_trace(
        {
            "problem_id": "linear-sat",
            "task": "math",
            "variables": [
                {"name": "x", "domain": "int", "bounds": {"lower": 0, "upper": 10}},
            ],
            "assumptions": [],
            "steps": [
                {
                    "id": 1,
                    "kind": "derive",
                    "expr": {
                        "type": "binary",
                        "op": ">=",
                        "left": {"type": "variable", "name": "x"},
                        "right": {"type": "constant", "value": 0},
                    },
                }
            ],
            "constraints": [
                {
                    "kind": "linear_ineq",
                    "terms": [{"variable": "x", "coefficient": 1}],
                    "relation": ">=",
                    "rhs": 5,
                },
                {
                    "kind": "linear_ineq",
                    "terms": [{"variable": "x", "coefficient": 1}],
                    "relation": "<=",
                    "rhs": 9,
                },
            ],
        }
    )

    result = check_trace(trace)
    assert result["status"] == "sat"
    assert result["model"]["x"] >= 5
    assert result["model"]["x"] <= 9


def test_conflicting_domains_unsat() -> None:
    trace = build_trace(
        {
            "problem_id": "conflict",
            "task": "math",
            "variables": [
                {"name": "x", "domain": "int"},
            ],
            "assumptions": [],
            "steps": [
                {
                    "id": 1,
                    "kind": "assume",
                    "expr": {
                        "type": "variable",
                        "name": "x",
                    },
                }
            ],
            "constraints": [
                {"kind": "int_domain", "variable": "x", "lower": 5, "upper": 6},
                {"kind": "int_domain", "variable": "x", "lower": 0, "upper": 1},
            ],
        }
    )

    result = check_trace(trace)
    assert result["status"] == "unsat"
    assert result.get("unsat_core")
    assert any(label.startswith("constraint:") for label in result["unsat_core"])


def test_all_different_constraint() -> None:
    trace = build_trace(
        {
            "problem_id": "all-diff",
            "task": "math",
            "variables": [
                {"name": "x", "domain": "int"},
                {"name": "y", "domain": "int"},
                {"name": "z", "domain": "int"},
            ],
            "assumptions": [],
            "steps": [
                {
                    "id": 1,
                    "kind": "derive",
                    "expr": {
                        "type": "binary",
                        "op": "=",
                        "left": {"type": "variable", "name": "x"},
                        "right": {"type": "constant", "value": 0},
                    },
                }
            ],
            "constraints": [
                {"kind": "all_different", "variables": ["x", "y", "z"]},
                {
                    "kind": "linear_ineq",
                    "terms": [{"variable": "y", "coefficient": 1}],
                    "relation": "=",
                    "rhs": 1,
                },
                {
                    "kind": "linear_ineq",
                    "terms": [{"variable": "z", "coefficient": 1}],
                    "relation": "=",
                    "rhs": 2,
                },
            ],
        }
    )

    result = check_trace(trace)
    assert result["status"] == "sat"
    model = result["model"]
    assert len({model["x"], model["y"], model["z"]}) == 3
