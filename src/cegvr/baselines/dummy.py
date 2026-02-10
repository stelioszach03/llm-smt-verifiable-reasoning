"""Simple baseline strategies that bypass the solver."""

from __future__ import annotations

from copy import deepcopy
from typing import Dict


def build_dummy_trace(problem: Dict) -> Dict:
    """Return a minimal trace that only contains an answer field."""

    variables = deepcopy(problem.get("variables", []))
    assignments: Dict[str, int | bool] = {}
    steps = []

    for index, variable in enumerate(variables, start=1):
        name = variable.get("name", f"var_{index}")
        domain = variable.get("domain", "int")
        if domain == "bool":
            value: int | bool = False
        else:
            value = 0
        assignments[name] = value
        steps.append(
            {
                "id": index,
                "kind": "derive",
                "expr": {
                    "type": "binary",
                    "op": "=",
                    "left": {"type": "variable", "name": name},
                    "right": {"type": "constant", "value": value},
                },
            }
        )

    return {
        "problem_id": str(problem.get("problem_id", "dummy-problem")),
        "task": problem.get("task", "math"),
        "variables": variables,
        "assumptions": [],
        "steps": steps,
        "constraints": [],
        "objective": {"type": "value"},
        "answer": {
            "value": assignments,
            "justification": "Dummy baseline without solver verification",
        },
    }


__all__ = ["build_dummy_trace"]
