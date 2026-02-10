"""Tests for ablation flags in the repair loop."""

from __future__ import annotations

from cegvr.engine.configs import ExperimentConfig
from cegvr.engine.repair import repair_until_certified
from cegvr.generation.provider import StubGenerator


PROBLEM = {
    "problem_id": "abl-test",
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


class NeedsRepairGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def propose(
        self, problem: dict, budget: int, hint: dict | None = None
    ) -> list[dict]:
        self.calls += 1
        if hint and any(
            issue.get("type") == "unsat_core" for issue in hint.get("issues", [])
        ):
            value = 2
            constraints = [problem["constraints"][0]]
        else:
            value = 0
            constraints = [
                problem["constraints"][0],
                {
                    "kind": "linear_ineq",
                    "terms": [{"variable": "x", "coefficient": 1}],
                    "relation": "=",
                    "rhs": 0,
                },
            ]
        trace = {
            "problem_id": problem["problem_id"],
            "task": problem["task"],
            "variables": problem["variables"],
            "assumptions": [],
            "steps": [
                {
                    "id": 1,
                    "kind": "derive",
                    "expr": {
                        "type": "binary",
                        "op": "=",
                        "left": {"type": "variable", "name": "x"},
                        "right": {"type": "constant", "value": value},
                    },
                }
            ],
            "constraints": constraints,
            "objective": {"type": "value"},
            "answer": {"value": {"x": value}, "justification": "abl-test"},
        }
        return [trace for _ in range(budget)]


class MissingConstraintGenerator:
    def propose(
        self, problem: dict, budget: int, hint: dict | None = None
    ) -> list[dict]:
        trace = {
            "problem_id": problem["problem_id"],
            "task": problem["task"],
            "variables": problem["variables"],
            "assumptions": [],
            "steps": [],
            "objective": {"type": "value"},
            "answer": {"value": {}, "justification": "missing constraints"},
        }
        return [trace for _ in range(budget)]


def test_no_solver_returns_baseline() -> None:
    config = ExperimentConfig(use_solver=False)
    result = repair_until_certified(PROBLEM, StubGenerator(seed=0), config=config)
    assert result["status"] == "baseline"
    assert result["config"]["use_solver"] is False
    assert result["solver_calls"] == 0


def test_no_repair_limits_iterations() -> None:
    generator = NeedsRepairGenerator()
    config = ExperimentConfig(enable_repair=False)
    result = repair_until_certified(
        PROBLEM, generator, config=config, per_round_budget=1
    )
    assert result["status"] != "certified"
    assert result["rounds"] == 1
    assert result["solver_calls"] == 1
    assert generator.calls == 1


def test_no_grammar_avoids_validation_failure() -> None:
    generator = MissingConstraintGenerator()
    default_result = repair_until_certified(PROBLEM, generator)
    assert default_result["status"] == "failed"

    config = ExperimentConfig(use_grammar=False)
    ablated_result = repair_until_certified(PROBLEM, generator, config=config)
    assert ablated_result["config"]["use_grammar"] is False
    assert ablated_result["status"] != "failed"
