"""Generate a solver-backed linear feasibility benchmark for CEGVR."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import random
from time import perf_counter
from typing import Iterable, List

import z3


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


def _linear_constraint(
    constraint_id: str,
    variable_specs: Iterable[VariableSpec],
    coefficients: Iterable[int],
    relation: str,
    rhs: int,
) -> dict:
    terms = [
        {"variable": spec.name, "coefficient": coeff}
        for spec, coeff in zip(variable_specs, coefficients)
    ]
    return {
        "constraint_id": constraint_id,
        "kind": "linear_ineq",
        "terms": terms,
        "relation": relation,
        "rhs": rhs,
        "offset": 0.0,
    }


def _sample_variables(rng: random.Random) -> List[VariableSpec]:
    num_vars = rng.randint(3, 6)
    variables: List[VariableSpec] = []
    for index in range(num_vars):
        upper = rng.randint(6, 12)
        variables.append(VariableSpec(name=f"x{index + 1}", lower=0, upper=upper))
    return variables


def _sample_witness(
    variable_specs: Iterable[VariableSpec], rng: random.Random
) -> dict[str, int]:
    return {
        spec.name: rng.randint(spec.lower, spec.upper) for spec in variable_specs
    }


def _build_sat_constraints(
    variable_specs: List[VariableSpec],
    witness: dict[str, int],
    rng: random.Random,
) -> list[dict]:
    constraints: list[dict] = []
    num_constraints = rng.randint(len(variable_specs) + 1, len(variable_specs) * 2 + 2)
    for index in range(num_constraints):
        coefficients = [rng.randint(1, 5) for _ in variable_specs]
        lhs = sum(coeff * witness[spec.name] for spec, coeff in zip(variable_specs, coefficients))
        relation = rng.choice(["<=", ">=", "="])
        if relation == "<=":
            rhs = lhs + rng.randint(0, 4)
        elif relation == ">=":
            rhs = lhs - rng.randint(0, 4)
        else:
            rhs = lhs
        constraints.append(
            _linear_constraint(
                f"c{index + 1}",
                variable_specs,
                coefficients,
                relation,
                rhs,
            )
        )
    return constraints


def _inject_unsat_constraints(
    variable_specs: List[VariableSpec],
    witness: dict[str, int],
    rng: random.Random,
    base_constraints: list[dict],
) -> list[dict]:
    constraints = list(base_constraints)
    target = rng.choice(variable_specs)
    value = witness[target.name]
    lower, upper = target.lower, target.upper

    if value < upper:
        lower_rhs = value + 1
        upper_rhs = value
        constraints.append(
            _linear_constraint(
                f"c{len(constraints) + 1}",
                [target],
                [1],
                ">=",
                lower_rhs,
            )
        )
        constraints.append(
            _linear_constraint(
                f"c{len(constraints) + 1}",
                [target],
                [1],
                "<=",
                upper_rhs,
            )
        )
    else:
        lower_rhs = value
        upper_rhs = max(lower, value - 1)
        constraints.append(
            _linear_constraint(
                f"c{len(constraints) + 1}",
                [target],
                [1],
                ">=",
                lower_rhs,
            )
        )
        constraints.append(
            _linear_constraint(
                f"c{len(constraints) + 1}",
                [target],
                [1],
                "<=",
                upper_rhs,
            )
        )
    return constraints


def _build_problem(index: int, label: str, rng: random.Random) -> dict:
    variables = _sample_variables(rng)
    witness = _sample_witness(variables, rng)
    sat_constraints = _build_sat_constraints(variables, witness, rng)

    if label == "sat":
        constraints = sat_constraints
        problem_id = f"linear-sat-{index:04d}"
    else:
        constraints = _inject_unsat_constraints(variables, witness, rng, sat_constraints)
        problem_id = f"linear-unsat-{index:04d}"

    offline = _offline_solver_stats(variables, constraints)
    metadata = {
        "type": f"linear_{label}",
        "difficulty_bin": _difficulty_bin(
            len(variables),
            len(constraints),
            offline["time_ms"],
        ),
        "n_vars": len(variables),
        "n_constraints": len(constraints),
        "constraint_to_var_ratio": len(constraints) / len(variables),
        "coeff_max_abs": _coeff_max_abs(constraints),
        "offline_solver_time_ms": offline["time_ms"],
        "unsat_core_size": offline["unsat_core_size"],
    }

    return {
        "problem_id": problem_id,
        "task": "math",
        "variables": [spec.as_dict() for spec in variables],
        "constraints": constraints,
        "ground_truth": label,
        "metadata": metadata,
    }


def _offline_solver_stats(variables: List[VariableSpec], constraints: list[dict]) -> dict:
    solver = z3.Solver()
    solver.set(unsat_core=True)
    symbols = {spec.name: z3.Int(spec.name) for spec in variables}
    for spec in variables:
        solver.assert_and_track(symbols[spec.name] >= spec.lower, f"d:{spec.name}:lower")
        solver.assert_and_track(symbols[spec.name] <= spec.upper, f"d:{spec.name}:upper")
    for constraint in constraints:
        expr = z3.Sum(
            *[
                z3.IntVal(int(term["coefficient"])) * symbols[term["variable"]]
                for term in constraint.get("terms", [])
            ]
        )
        rhs = z3.IntVal(int(constraint["rhs"]))
        relation = constraint["relation"]
        if relation == "<=":
            tracked = expr <= rhs
        elif relation == ">=":
            tracked = expr >= rhs
        else:
            tracked = expr == rhs
        solver.assert_and_track(tracked, str(constraint["constraint_id"]))

    start = perf_counter()
    result = solver.check()
    elapsed_ms = (perf_counter() - start) * 1000.0
    return {
        "result": str(result),
        "time_ms": elapsed_ms,
        "unsat_core_size": len(solver.unsat_core()) if result == z3.unsat else 0,
    }


def _coeff_max_abs(constraints: list[dict]) -> int:
    coeffs = [
        abs(int(term["coefficient"]))
        for constraint in constraints
        if constraint.get("kind") == "linear_ineq"
        for term in constraint.get("terms", [])
    ]
    return max(coeffs) if coeffs else 0


def _difficulty_bin(n_vars: int, n_constraints: int, time_ms: float) -> str:
    score = n_vars + n_constraints + (1 if time_ms > 10.0 else 0)
    if score <= 10:
        return "easy"
    if score <= 16:
        return "medium"
    return "hard"


def build_dataset(total: int, sat_ratio: float, seed: int) -> List[dict]:
    rng = random.Random(seed)
    sat_count = max(1, round(total * sat_ratio))
    sat_count = min(sat_count, total - 1) if total > 1 else total
    unsat_count = total - sat_count

    problems: List[dict] = []
    for index in range(sat_count):
        problems.append(_build_problem(index, "sat", rng))
    for index in range(unsat_count):
        problems.append(_build_problem(index, "unsat", rng))
    rng.shuffle(problems)
    return problems


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a solver-backed linear feasibility dataset for CEGVR."
    )
    parser.add_argument(
        "--total", type=int, default=500, help="Total number of problems to generate."
    )
    parser.add_argument(
        "--sat-ratio", type=float, default=0.6, help="Ratio of satisfiable instances."
    )
    parser.add_argument(
        "--seed", type=int, default=7, help="Random seed for reproducibility."
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT, help="Destination JSONL file."
    )
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
