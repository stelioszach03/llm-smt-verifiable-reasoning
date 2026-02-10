"""Property-based tests for linear constraint encodings."""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given, settings
from hypothesis.strategies import composite

from cegvr.grammar.types import Trace
from cegvr.smt.runner import check_trace


def make_trace(lower: int, upper: int, value: int | None = None) -> Trace:
    constraints = [
        {"kind": "int_domain", "variable": "x", "lower": lower, "upper": upper},
    ]
    if value is not None:
        constraints.append(
            {
                "kind": "linear_ineq",
                "terms": [{"variable": "x", "coefficient": 1.0}],
                "relation": "=",
                "rhs": value,
            }
        )
    trace_dict = {
        "problem_id": "prop-test",
        "task": "math",
        "variables": [
            {"name": "x", "domain": "int", "bounds": {"lower": lower, "upper": upper}}
        ],
        "assumptions": [],
        "steps": [
            {
                "id": 0,
                "kind": "assume",
                "expr": {
                    "type": "binary",
                    "op": "=",
                    "left": {"type": "variable", "name": "x"},
                    "right": {
                        "type": "constant",
                        "value": lower if value is None else value,
                    },
                },
            }
        ],
        "constraints": constraints,
        "objective": {"type": "value"},
    }
    return Trace.model_validate(trace_dict)


@composite
def inverted_bounds_cases(draw) -> tuple[int, int]:
    upper = draw(st.integers(min_value=-100, max_value=100))
    gap = draw(st.integers(min_value=1, max_value=50))
    lower = upper + gap
    return lower, upper


@composite
def feasible_cases(draw) -> tuple[int, int, int]:
    lower = draw(st.integers(min_value=-50, max_value=50))
    upper = draw(st.integers(min_value=lower, max_value=lower + 50))
    value = draw(st.integers(min_value=lower, max_value=upper))
    return lower, upper, value


@settings(max_examples=50)
@given(inverted_bounds_cases())
def test_inverted_bounds_are_unsat(bounds: tuple[int, int]) -> None:
    lower, upper = bounds
    trace = make_trace(lower, upper)
    result = check_trace(trace)
    assert result["status"] == "unsat"


@settings(max_examples=50)
@given(feasible_cases())
def test_feasible_assignments_satisfy_bounds(case: tuple[int, int, int]) -> None:
    lower, upper, value = case
    trace = make_trace(lower, upper, value=value)
    result = check_trace(trace)
    assert result["status"] == "sat"
    model = result["model"]
    assert lower <= model["x"] <= upper
