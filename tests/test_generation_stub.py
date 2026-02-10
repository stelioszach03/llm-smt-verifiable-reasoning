"""Tests for the stub trace generator."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from cegvr.generation.provider import StubGenerator


def load_schema() -> dict:
    schema_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "cegvr"
        / "grammar"
        / "schema.json"
    )
    return json.loads(schema_path.read_text(encoding="utf-8"))


def test_stub_generator_produces_valid_traces() -> None:
    schema = load_schema()
    generator = StubGenerator(seed=42)
    problem = {
        "problem_id": "unit-test",
        "task": "math",
        "variables": [
            {"name": "x", "domain": "int", "bounds": {"lower": 0, "upper": 3}},
            {"name": "flag", "domain": "bool"},
        ],
    }

    traces = generator.propose(problem, budget=5)
    assert len(traces) == 5

    for trace in traces:
        jsonschema.validate(instance=trace, schema=schema)
        assert trace["problem_id"].startswith("unit-test")
        assert trace["variables"][0]["name"] == "x"


def test_stub_generator_respects_budget_zero() -> None:
    generator = StubGenerator(seed=123)
    traces = generator.propose(
        {
            "problem_id": "zero-budget",
            "task": "math",
            "variables": [{"name": "x", "domain": "int"}],
        },
        budget=0,
    )
    assert traces == []
