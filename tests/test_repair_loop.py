"""Unit tests for the repair loop."""

from __future__ import annotations

from copy import deepcopy

from cegvr.engine.repair import repair_until_certified
from cegvr.generation.provider import TraceGenerator


def make_trace(problem: dict, assignments: dict[str, int | bool]) -> dict:
    """Helper to build a schema-compliant trace for tests."""

    variables = deepcopy(problem["variables"])
    constraints = deepcopy(problem.get("constraints", []))
    steps = []
    assumptions = []

    for idx, spec in enumerate(variables, start=1):
        name = spec["name"]
        domain = spec.get("domain", "int")
        value = assignments[name]

        if domain == "bool":
            constraints.append(
                {"kind": "bool_atom", "variable": name, "value": bool(value)}
            )
        else:
            constraints.append(
                {
                    "kind": "linear_ineq",
                    "terms": [{"variable": name, "coefficient": 1}],
                    "relation": "=",
                    "rhs": int(value),
                }
            )
        steps.append(
            {
                "id": idx,
                "kind": "derive",
                "expr": {
                    "type": "binary",
                    "op": "=",
                    "left": {"type": "variable", "name": name},
                    "right": {"type": "constant", "value": value},
                },
            }
        )
        assumptions.append(f"{name} fixed to {value}")

    return {
        "problem_id": problem.get("problem_id", "test-problem"),
        "task": problem.get("task", "math"),
        "variables": variables,
        "assumptions": assumptions,
        "steps": steps,
        "constraints": constraints,
        "objective": {"type": "value"},
        "answer": {"value": assignments, "justification": "unit-test"},
    }


class SingleShotGenerator:
    def propose(
        self, problem: dict, budget: int, hint: dict | None = None
    ) -> list[dict]:
        trace = make_trace(problem, {"x": 2})
        return [trace for _ in range(budget)]


class UnsatGenerator:
    def propose(
        self, problem: dict, budget: int, hint: dict | None = None
    ) -> list[dict]:
        trace = make_trace(problem, {"x": 0})
        return [trace for _ in range(budget)]


class RepairGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def propose(
        self, problem: dict, budget: int, hint: dict | None = None
    ) -> list[dict]:
        self.calls += 1
        fix = False
        if hint and isinstance(hint, dict):
            for issue in hint.get("issues", []):
                if issue.get("type") == "unsat_core":
                    fix = True
                    break
        assignments = {"x": 2, "flag": True} if fix else {"x": 0, "flag": False}
        trace = make_trace(problem, assignments)
        return [trace for _ in range(budget)]


SAT_PROBLEM = {
    "problem_id": "sat-problem",
    "task": "math",
    "variables": [{"name": "x", "domain": "int", "bounds": {"lower": 0, "upper": 5}}],
    "constraints": [
        {
            "kind": "linear_ineq",
            "terms": [{"variable": "x", "coefficient": 1}],
            "relation": "=",
            "rhs": 2,
        }
    ],
}


UNSAT_PROBLEM = {
    "problem_id": "unsat-problem",
    "task": "math",
    "variables": [{"name": "x", "domain": "int", "bounds": {"lower": 0, "upper": 5}}],
    "constraints": [
        {
            "kind": "linear_ineq",
            "terms": [{"variable": "x", "coefficient": 1}],
            "relation": "=",
            "rhs": 2,
        },
        {
            "kind": "linear_ineq",
            "terms": [{"variable": "x", "coefficient": 1}],
            "relation": "=",
            "rhs": 3,
        },
    ],
}


REPAIR_PROBLEM = {
    "problem_id": "repair-problem",
    "task": "math",
    "variables": [
        {"name": "x", "domain": "int", "bounds": {"lower": 0, "upper": 5}},
        {"name": "flag", "domain": "bool"},
    ],
    "constraints": [
        {
            "kind": "linear_ineq",
            "terms": [{"variable": "x", "coefficient": 1}],
            "relation": "=",
            "rhs": 2,
        },
        {"kind": "bool_atom", "variable": "flag", "value": True},
    ],
}


def test_repair_loop_certifies_sat_problem() -> None:
    result = repair_until_certified(
        SAT_PROBLEM, SingleShotGenerator(), max_rounds=3, per_round_budget=1
    )
    assert result["status"] == "certified"
    assert result["rounds"] == 1
    assert result["model"]["x"] == 2


def test_repair_loop_unsat_problem_fails() -> None:
    result = repair_until_certified(
        UNSAT_PROBLEM, UnsatGenerator(), max_rounds=2, per_round_budget=1
    )
    assert result["status"] == "failed"
    assert result["rounds"] == 2
    assert result["history"]


def test_repair_loop_uses_feedback_for_fix() -> None:
    generator = RepairGenerator()
    result = repair_until_certified(
        REPAIR_PROBLEM, generator, max_rounds=3, per_round_budget=1
    )
    assert result["status"] == "certified"
    assert result["rounds"] == 2
    assert result["model"]["flag"] is True
    assert generator.calls >= 2
