"""Validation tests for reasoning trace schema utilities."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from cegvr.grammar.types import Trace
from cegvr.grammar.validate import load_trace, validate_trace_json


@pytest.fixture
def valid_trace_payload() -> dict:
    return {
        "problem_id": "demo-problem",
        "task": "math",
        "variables": [
            {
                "name": "x",
                "domain": "int",
                "bounds": {"lower": 0, "upper": 10},
            },
            {
                "name": "flag",
                "domain": "bool",
            },
        ],
        "assumptions": ["x >= 0"],
        "steps": [
            {
                "id": 1,
                "kind": "assume",
                "expr": {
                    "type": "binary",
                    "op": "<=",
                    "left": {"type": "variable", "name": "x"},
                    "right": {"type": "constant", "value": 10},
                },
            }
        ],
        "constraints": [
            {
                "kind": "linear_ineq",
                "terms": [{"variable": "x", "coefficient": 1.0}],
                "relation": "<=",
                "rhs": 10,
                "offset": 0.0,
            }
        ],
        "objective": {"type": "value"},
        "answer": {
            "value": {"x": 4, "flag": True},
            "justification": "Feasible assignment",
        },
    }


def test_validate_trace_json_accepts_valid_payload(valid_trace_payload: dict) -> None:
    trace = validate_trace_json(valid_trace_payload)
    assert isinstance(trace, Trace)
    assert trace.variables[0].name == "x"
    assert trace.steps[0].expr.type == "binary"


def test_validate_trace_json_rejects_boolean_bounds(valid_trace_payload: dict) -> None:
    invalid_payload = deepcopy(valid_trace_payload)
    invalid_payload["variables"][1]["bounds"] = {"lower": 0}

    with pytest.raises(ValidationError) as exc_info:
        validate_trace_json(invalid_payload)

    error = exc_info.value.errors()[0]
    assert error["loc"][0:2] == ("variables", 1)
    assert "boolean variables cannot specify bounds" in error["msg"]


def test_validate_trace_json_rejects_empty_linear_terms(
    valid_trace_payload: dict,
) -> None:
    invalid_payload = deepcopy(valid_trace_payload)
    invalid_payload["constraints"][0]["terms"] = []

    with pytest.raises(ValidationError) as exc_info:
        validate_trace_json(invalid_payload)

    error = exc_info.value.errors()[0]
    assert error["loc"] == ("constraints", 0, "terms")
    assert "at least one term" in error["msg"]


def test_load_trace_reads_from_disk(valid_trace_payload: dict, tmp_path: Path) -> None:
    target = tmp_path / "trace.json"
    target.write_text(json.dumps(valid_trace_payload), encoding="utf-8")

    trace = load_trace(target)
    assert trace.problem_id == "demo-problem"
    assert trace.answer is not None
