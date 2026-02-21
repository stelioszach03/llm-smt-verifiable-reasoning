"""Tests for conflict-directed search helpers."""

from __future__ import annotations

from cegvr.candidate.repair import (
    _constraint_variables,
    _failure_signature,
    _variables_from_constraint_ids,
)


def test_constraint_variables_extracts_nested_variables() -> None:
    constraint = {
        "kind": "and",
        "constraints": [
            {
                "kind": "linear_ineq",
                "terms": [{"variable": "x", "coefficient": 1}],
                "relation": "=",
                "rhs": 2,
            },
            {
                "kind": "not",
                "constraint": {
                    "kind": "bool_atom",
                    "variable": "flag",
                    "value": True,
                },
            },
            {"kind": "all_different", "variables": ["y", "z"]},
        ],
    }

    assert _constraint_variables(constraint) == {"x", "flag", "y", "z"}


def test_failure_signature_sorts_constraint_ids() -> None:
    signature = _failure_signature(
        failure_type="constraint_violation",
        verifier_result="unsat",
        predicted_status="sat",
        constraint_ids=["c2", "c1"],
    )

    assert signature == ("constraint_violation", "unsat", "sat", "c1", "c2")


def test_variables_from_constraint_ids_collect_union() -> None:
    variable_map = {
        "c1": ["x", "y"],
        "c2": ["y", "z"],
    }

    assert _variables_from_constraint_ids(variable_map, ["c2", "c1"]) == [
        "x",
        "y",
        "z",
    ]
