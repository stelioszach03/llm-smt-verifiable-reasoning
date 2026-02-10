"""Variation generators for problem specifications."""

from __future__ import annotations

from copy import deepcopy
from typing import Dict, List


def perturb_bounds(problem: Dict, offset: int) -> Dict:
    variant = deepcopy(problem)
    for variable in variant.get("variables", []):
        bounds = variable.get("bounds")
        if (
            bounds
            and "lower" in bounds
            and "upper" in bounds
            and isinstance(bounds["lower"], (int, float))
            and isinstance(bounds["upper"], (int, float))
        ):
            bounds["lower"] = bounds["lower"] + offset
            bounds["upper"] = bounds["upper"] + offset
    return variant


def vary_objective(problem: Dict, sign: int) -> Dict:
    variant = deepcopy(problem)
    objective = variant.get("objective") or {}
    if objective.get("type") in {"minimize", "maximize"} and "target" in objective:
        target = objective.get("target")
        if isinstance(target, dict):
            target["type"] = target.get("type", "variable")
            target["name"] = f"{target.get('name', 'obj')}"  # ensure name present
        objective["type"] = "maximize" if sign > 0 else "minimize"
    else:
        objective["type"] = "value"
    variant["objective"] = objective
    return variant


def generate_variants(problem: Dict, count: int) -> List[Dict]:
    variants: List[Dict] = []
    for idx in range(count):
        if idx % 2 == 0:
            variants.append(perturb_bounds(problem, offset=idx + 1))
        else:
            variants.append(vary_objective(problem, sign=(-1) ** idx))
    return variants


__all__ = ["perturb_bounds", "vary_objective", "generate_variants"]
