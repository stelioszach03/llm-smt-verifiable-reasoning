"""Utility script for generating a linear feasibility dataset for CEGVR."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import random
from typing import Iterable, List


DEFAULT_OUTPUT = Path("data/linear/problems.jsonl")


@dataclass
class VariableSpec:
    name: str
    lower: int
    upper: int

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "domain": "int",
            "bounds": {"lower": self.lower, "upper": self.upper},
        }


def _linear_constraint(variable_specs: Iterable[VariableSpec], coefficients: Iterable[int], relation: str, rhs: int) -> dict:
    terms = [
        {"variable": spec.name, "coefficient": coeff}
        for spec, coeff in zip(variable_specs, coefficients)
    ]
    return {
        "kind": "linear_ineq",
        "terms": terms,
        "relation": relation,
        "rhs": rhs,
        "offset": 0.0,
    }


def _build_feasible_problem(index: int, rng: random.Random) -> dict:
    num_vars = rng.randint(2, 4)
    variables: List[VariableSpec] = []
    for i in range(num_vars):
        upper = rng.randint(4, 9)
        variables.append(VariableSpec(name=f"x{i+1}", lower=0, upper=upper))

    coefficients = [rng.randint(1, 4) for _ in range(num_vars)]
    max_sum = sum(coeff * var.upper for coeff, var in zip(coefficients, variables))

    constraints = [
        _linear_constraint(variables, coefficients, "<=", max_sum),
        _linear_constraint(variables, coefficients, ">=", 0),
    ]

    metadata = {
        "type": "linear_feasible",
        "coefficients": coefficients,
        "upper_limit": max_sum,
    }

    problem = {
        "problem_id": f"linear-sat-{index:04d}",
        "task": "math",
        "variables": [spec.as_dict() for spec in variables],
        "constraints": constraints,
        "ground_truth": "sat",
        "metadata": metadata,
    }
    return problem


def _build_infeasible_problem(index: int, rng: random.Random) -> dict:
    num_vars = rng.randint(2, 4)
    variables: List[VariableSpec] = []
    for i in range(num_vars):
        upper = rng.randint(2, 4)
        variables.append(VariableSpec(name=f"y{i+1}", lower=0, upper=upper))

    coefficients = [rng.randint(2, 5) for _ in range(num_vars)]
    max_sum = sum(coeff * var.upper for coeff, var in zip(coefficients, variables))
    infeasible_rhs = max_sum + rng.randint(1, 3)

    constraints = [
        _linear_constraint(variables, coefficients, ">=", infeasible_rhs),
    ]

    metadata = {
        "type": "linear_infeasible",
        "coefficients": coefficients,
        "required_sum": infeasible_rhs,
        "max_supported_sum": max_sum,
    }

    problem = {
        "problem_id": f"linear-unsat-{index:04d}",
        "task": "math",
        "variables": [spec.as_dict() for spec in variables],
        "constraints": constraints,
        "ground_truth": "unsat",
        "metadata": metadata,
    }
    return problem


def build_dataset(total: int, sat_ratio: float, seed: int) -> List[dict]:
    rng = random.Random(seed)
    sat_count = max(1, round(total * sat_ratio))
    sat_count = min(sat_count, total - 1) if total > 1 else total
    unsat_count = total - sat_count

    problems: List[dict] = []

    for idx in range(sat_count):
        problems.append(_build_feasible_problem(idx, rng))

    for idx in range(unsat_count):
        problems.append(_build_infeasible_problem(idx, rng))

    rng.shuffle(problems)
    return problems


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a linear feasibility dataset for CEGVR.")
    parser.add_argument("--total", type=int, default=200, help="Total number of problems to generate.")
    parser.add_argument("--sat-ratio", type=float, default=0.6, help="Ratio of satisfiable instances.")
    parser.add_argument("--seed", type=int, default=7, help="Random seed for reproducibility.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Destination JSONL file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    problems = build_dataset(total=args.total, sat_ratio=args.sat_ratio, seed=args.seed)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for problem in problems:
            handle.write(json.dumps(problem, ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    sat = sum(1 for problem in problems if problem["ground_truth"] == "sat")
    unsat = len(problems) - sat
    print(f"Wrote {len(problems)} problems to {args.output} (sat={sat}, unsat={unsat}).")


if __name__ == "__main__":
    main()
