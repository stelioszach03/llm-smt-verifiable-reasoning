"""Adapters to transform raw dataset entries into normalized specs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

DEFAULT_OBJECTIVE = {"type": "value"}


def normalize_variable(variable: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure a variable dictionary has the expected keys."""

    name = str(variable.get("name"))
    if not name:
        raise ValueError("Variable entries must include a non-empty 'name'")
    domain = variable.get("domain", "int")
    bounds = variable.get("bounds")
    normalized = {"name": name, "domain": domain}
    if bounds is not None:
        normalized["bounds"] = bounds
    return normalized


def normalize_problem(problem: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise raw problems into the structure expected by generators/solvers."""

    if "variables" not in problem:
        raise ValueError("Problem dictionaries must include a 'variables' field")

    normalized_variables = [
        normalize_variable(variable) for variable in problem["variables"]
    ]
    constraints = deepcopy(problem.get("constraints", []))
    objective = deepcopy(problem.get("objective") or DEFAULT_OBJECTIVE)

    metadata = {
        key: deepcopy(value)
        for key, value in problem.items()
        if key not in {"problem_id", "task", "variables", "constraints", "objective"}
    }

    return {
        "problem_id": str(problem.get("problem_id", "unnamed-problem")),
        "task": problem.get("task", "math"),
        "variables": normalized_variables,
        "constraints": constraints,
        "objective": objective,
        "metadata": metadata,
    }


def batch_normalize(problems: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize a list of problems."""

    return [normalize_problem(problem) for problem in problems]


__all__ = [
    "normalize_problem",
    "normalize_variable",
    "batch_normalize",
    "DEFAULT_OBJECTIVE",
]
