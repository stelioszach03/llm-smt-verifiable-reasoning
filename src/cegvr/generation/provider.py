"""Trace generation provider interfaces and stubs."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import random
from typing import Any, Dict, Protocol, runtime_checkable

from cegvr.utils.random import generate_seed


@runtime_checkable
class TraceGenerator(Protocol):
    """Interface for proposing candidate reasoning traces."""

    def propose(
        self, problem: dict, budget: int, hint: dict | None = None
    ) -> list[dict]:
        """Return up to ``budget`` candidate trace dictionaries for the given problem."""


@dataclass
class StubGenerator:
    """Heuristic generator that synthesizes toy traces for experimentation."""

    seed: int | None = None

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed or generate_seed())

    def propose(
        self, problem: dict, budget: int, hint: dict | None = None
    ) -> list[dict]:
        if budget <= 0:
            return []

        base_problem = deepcopy(problem)
        problem_id = str(base_problem.get("problem_id", "stub-problem"))
        task = base_problem.get("task", "math")
        variables = base_problem.get("variables", [])
        if not variables:
            raise ValueError("Problem specification must include at least one variable")

        forced_assignments = self._extract_forced_assignments(hint)
        proposals: list[dict] = []
        for index in range(budget):
            proposals.append(
                self._build_trace(
                    index=index,
                    problem_id=problem_id,
                    task=task,
                    variable_specs=variables,
                    base_constraints=base_problem.get("constraints", []),
                    forced_assignments=forced_assignments,
                )
            )
        return proposals

    def _build_trace(
        self,
        *,
        index: int,
        problem_id: str,
        task: str,
        variable_specs: list[dict],
        base_constraints: list[dict],
        forced_assignments: Dict[str, Any],
    ) -> dict:
        assignment: dict[str, int | bool] = {}
        steps: list[dict] = []
        assumptions: list[str] = []
        constraints: list[dict] = [
            deepcopy(constraint) for constraint in base_constraints
        ]

        for local_id, spec in enumerate(variable_specs, start=1):
            name = spec["name"]
            domain = spec.get("domain", "int")
            bounds = spec.get("bounds") or {}

            value: int | bool
            if domain == "int":
                lower = int(bounds.get("lower", 0))
                upper = int(bounds.get("upper", lower + 5))
                if upper < lower:
                    upper = lower
                if name in forced_assignments:
                    forced_value = int(forced_assignments[name])
                    value = max(lower, min(upper, forced_value))
                else:
                    span = upper - lower + 1
                    offset = self._rng.randint(0, max(span - 1, 0))
                    value = lower + offset
                constraints.append(
                    {
                        "kind": "int_domain",
                        "variable": name,
                        "lower": lower,
                        "upper": upper,
                    }
                )
                constraints.append(
                    {
                        "kind": "linear_ineq",
                        "terms": [{"variable": name, "coefficient": 1}],
                        "relation": "=",
                        "rhs": value,
                    }
                )
                assumptions.append(f"{name} in [{lower}, {upper}]")
            else:
                if name in forced_assignments:
                    value = bool(forced_assignments[name])
                else:
                    value = bool((index + local_id) % 2 == 0)
                constraints.append(
                    {
                        "kind": "bool_atom",
                        "variable": name,
                        "value": value,
                    }
                )
                assumptions.append(f"{name} is {'true' if value else 'false'} in stub")

            assignment[name] = value

            steps.append(
                {
                    "id": local_id,
                    "kind": "derive",
                    "expr": {
                        "type": "binary",
                        "op": "=",
                        "left": {"type": "variable", "name": name},
                        "right": {"type": "constant", "value": value},
                    },
                    "note": f"Stub assignment for {name}",
                }
            )

        trace = {
            "problem_id": f"{problem_id}-stub-{index}",
            "task": task if task in {"math", "scheduling", "planning"} else "math",
            "variables": deepcopy(variable_specs),
            "assumptions": assumptions,
            "steps": steps,
            "constraints": constraints,
            "objective": {"type": "value"},
            "answer": {
                "value": assignment,
                "justification": "Stub generator deterministic assignment",
            },
        }
        return trace

    @staticmethod
    def _extract_forced_assignments(hint: dict | None) -> Dict[str, Any]:
        if not hint:
            return {}
        assignments: Dict[str, Any] = {}
        if not isinstance(hint, dict):
            return assignments
        for key in ("force_assignments", "suggested_assignments"):
            payload = hint.get(key)
            if isinstance(payload, dict):
                assignments.update(payload)
        return assignments


__all__ = ["TraceGenerator", "StubGenerator"]
