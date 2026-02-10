"""Prompt construction utilities for external trace generators."""

from __future__ import annotations

import json
from textwrap import indent
from typing import Any, Dict


def build_trace_prompt(problem_spec: Dict[str, Any], schema: Dict[str, Any]) -> str:
    """Return an instruction string coercing an LLM to emit JSON-only traces."""

    schema_str = json.dumps(schema, indent=2, sort_keys=True)
    example_trace = {
        "problem_id": problem_spec.get("problem_id", "example-problem"),
        "task": problem_spec.get("task", "math"),
        "variables": problem_spec.get(
            "variables",
            [
                {"name": "x", "domain": "int", "bounds": {"lower": 0, "upper": 3}},
                {"name": "flag", "domain": "bool"},
            ],
        ),
        "assumptions": ["Stub assumption only for illustration"],
        "steps": [
            {
                "id": 1,
                "kind": "derive",
                "expr": {
                    "type": "binary",
                    "op": "=",
                    "left": {"type": "variable", "name": "x"},
                    "right": {"type": "constant", "value": 1},
                },
            }
        ],
        "constraints": [
            {
                "kind": "linear_ineq",
                "terms": [{"variable": "x", "coefficient": 1}],
                "relation": "<=",
                "rhs": 3,
            }
        ],
        "objective": {"type": "value"},
        "answer": {
            "value": {"x": 1, "flag": True},
            "justification": "Feasible sample",
        },
    }
    example_str = json.dumps(example_trace, indent=2, sort_keys=True)

    instructions = f"""
You are given a problem specification and a JSON Schema. Produce a SINGLE valid JSON
object that represents a reasoning trace for the problem.
IMPORTANT RULES:
1. Respond with JSON only. Do not include prose, Markdown, or code fences.
2. Follow the schema exactly; omit optional fields if you cannot justify their values.
3. Ensure every array, object, and value satisfies type constraints.

Problem specification:
{indent(json.dumps(problem_spec, indent=2, sort_keys=True), "  ")}

JSON Schema:
{indent(schema_str, "  ")}

Example output (for illustration only):
{indent(example_str, "  ")}

Now emit the JSON trace for the provided problem.
"""
    return instructions.strip()


__all__ = ["build_trace_prompt"]
