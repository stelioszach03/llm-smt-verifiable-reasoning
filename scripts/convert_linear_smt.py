"""Convert SMT-LIB linear arithmetic instances to CEGVR JSONL."""

from __future__ import annotations

import argparse
import json
import math
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from z3 import Real, Solver, Sum, sat, unsat


LINEAR_BOUND = 100


@dataclass
class LinearIneq:
    coefficients: Dict[str, float]
    relation: str
    rhs: float

    def to_cegvr(self) -> dict:
        return {
            "kind": "linear_ineq",
            "terms": [
                {"variable": var, "coefficient": coeff}
                for var, coeff in sorted(self.coefficients.items())
            ],
            "relation": self.relation,
            "rhs": self.rhs,
            "offset": 0.0,
        }


def tokenize(text: str) -> List[str]:
    import re

    pattern = re.compile(r"\(|\)|[^()\s]+")
    return pattern.findall(text)


def parse(tokens: List[str], pos: int = 0):
    if pos >= len(tokens):
        raise ValueError("Unexpected end of input")
    token = tokens[pos]
    if token == "(":
        items = []
        pos += 1
        while pos < len(tokens) and tokens[pos] != ")":
            node, pos = parse(tokens, pos)
            items.append(node)
        if pos >= len(tokens):
            raise ValueError("Missing closing parenthesis")
        return items, pos + 1
    if token == ")":
        raise ValueError("Unbalanced parenthesis")
    return convert_atom(token), pos + 1


def convert_atom(token: str):
    if token.startswith("\"") and token.endswith("\""):
        return token[1:-1]
    try:
        if "." in token or "e" in token.lower():
            return float(token)
        return int(token)
    except ValueError:
        return token


def parse_constant(node) -> float:
    if isinstance(node, (int, float)):
        return float(node)
    if isinstance(node, list) and node and node[0] == "/":
        numerator = parse_constant(node[1])
        denominator = parse_constant(node[2])
        return numerator / denominator
    raise ValueError(f"Unsupported constant expression: {node}")


def parse_linear_expr(node) -> Tuple[Dict[str, float], float]:
    if isinstance(node, str):
        return {node: 1.0}, 0.0
    if isinstance(node, (int, float)):
        return {}, float(node)
    if not isinstance(node, list) or not node:
        raise ValueError(f"Unexpected node: {node}")

    head = node[0]
    if head == "+":
        coeffs: Dict[str, float] = {}
        const = 0.0
        for child in node[1:]:
            child_coeffs, child_const = parse_linear_expr(child)
            for var, coeff in child_coeffs.items():
                coeffs[var] = coeffs.get(var, 0.0) + coeff
            const += child_const
        return coeffs, const
    if head == "-":
        if len(node) == 2:
            coeffs, const = parse_linear_expr(node[1])
            return {var: -coeff for var, coeff in coeffs.items()}, -const
        left_coeffs, left_const = parse_linear_expr(node[1])
        right_coeffs, right_const = parse_linear_expr(node[2])
        coeffs = left_coeffs.copy()
        for var, coeff in right_coeffs.items():
            coeffs[var] = coeffs.get(var, 0.0) - coeff
        const = left_const - right_const
        return coeffs, const
    if head == "*":
        if len(node) != 3:
            raise ValueError("Unsupported multiplication arity")
        if isinstance(node[1], (int, float, list)):
            factor = parse_constant(node[1])
            coeffs, const = parse_linear_expr(node[2])
        else:
            factor = parse_constant(node[2])
            coeffs, const = parse_linear_expr(node[1])
        coeffs = {var: coeff * factor for var, coeff in coeffs.items()}
        return coeffs, const * factor
    if head == "ite":
        then_coeffs, then_const = parse_linear_expr(node[2])
        else_coeffs, else_const = parse_linear_expr(node[3])
        coeffs = {}
        for var in set(then_coeffs) | set(else_coeffs):
            coeffs[var] = (then_coeffs.get(var, 0.0) + else_coeffs.get(var, 0.0)) / 2
        const = (then_const + else_const) / 2
        return coeffs, const
    raise ValueError(f"Unsupported linear expression: {node}")


def parse_comparison(node) -> LinearIneq:
    if not isinstance(node, list) or len(node) != 3:
        raise ValueError(f"Invalid comparison node: {node}")
    comparator = node[0]
    left_coeffs, left_const = parse_linear_expr(node[1])
    right_coeffs, right_const = parse_linear_expr(node[2])
    coeffs = left_coeffs.copy()
    for var, coeff in right_coeffs.items():
        coeffs[var] = coeffs.get(var, 0.0) - coeff
    rhs = right_const - left_const
    relation_map = {
        "<=": "<=",
        "<": "<=",
        ">=": ">=",
        ">": ">=",
        "=": "=",
    }
    relation = relation_map.get(comparator)
    if relation is None:
        raise ValueError(f"Unsupported comparator: {comparator}")
    if comparator == "<":
        rhs -= 1e-6
    if comparator == ">":
        rhs += 1e-6
    return LinearIneq(coeffs, relation, rhs)


def flatten_formula(node) -> List[LinearIneq]:
    node = expand_let(node)
    if isinstance(node, list) and node:
        head = node[0]
        if head == "and":
            inequalities: List[LinearIneq] = []
            for child in node[1:]:
                inequalities.extend(flatten_formula(child))
            return inequalities
        if head == "not":
            return []
        return [parse_comparison(node)]
    raise ValueError("Unexpected SMT formula structure")


def parse_smt_problem(path: Path) -> Tuple[List[str], List[LinearIneq]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    tokens = tokenize(f"(begin {text} end)")
    sexpr, pos = parse(tokens)
    if pos != len(tokens):
        raise ValueError("Parsing did not consume all tokens")
    variables: List[str] = []
    inequalities: List[LinearIneq] = []
    for item in sexpr[1:-1]:
        if isinstance(item, list) and item:
            head = item[0]
            if head == "declare-fun" and len(item) >= 2:
                variables.append(str(item[1]))
            elif head == "assert" and len(item) == 2:
                inequalities.extend(flatten_formula(item[1]))
    return variables, inequalities


def build_z3_constraints(variables: List[str], inequalities: List[LinearIneq]):
    z3_vars = {name: Real(name) for name in variables}
    constraints = []
    for inequality in inequalities:
        expr = Sum([coeff * z3_vars[var] for var, coeff in inequality.coefficients.items()])
        if inequality.relation == "<=":
            constraints.append(expr <= inequality.rhs)
        elif inequality.relation == ">=":
            constraints.append(expr >= inequality.rhs)
        else:
            constraints.append(expr == inequality.rhs)
    return z3_vars, constraints


def convert_smt_file(path: Path) -> dict | None:
    try:
        variables, inequalities = parse_smt_problem(path)
    except Exception:
        return None
    if not variables or not inequalities:
        return None
    _, z3_constraints = build_z3_constraints(variables, inequalities)
    solver = Solver()
    solver.add(z3_constraints)
    result = solver.check()
    if result == sat:
        ground_truth = "sat"
    elif result == unsat:
        ground_truth = "unsat"
    else:
        return None
    problem = {
        "problem_id": f"linear-{path.stem}",
        "task": "math",
        "variables": [
            {
                "name": name,
                "domain": "int",
                "bounds": {"lower": -LINEAR_BOUND, "upper": LINEAR_BOUND},
            }
            for name in variables
        ],
        "constraints": [ineq.to_cegvr() for ineq in inequalities],
        "ground_truth": ground_truth,
        "metadata": {"source": str(path)},
    }
    return problem


def expand_let(node, env: Dict[str, object] | None = None):
    if env is None:
        env = {}
    if isinstance(node, str):
        if node in env:
            return env[node]
        return node
    if isinstance(node, (int, float)):
        return node
    if not isinstance(node, list) or not node:
        return node
    head = node[0]
    if head == "let" and len(node) == 3:
        local_env = env.copy()
        bindings = node[1]
        body = node[2]
        for binding in bindings:
            if isinstance(binding, list) and len(binding) == 2:
                name = binding[0]
                value = expand_let(binding[1], local_env)
                local_env[name] = value
        return expand_let(body, local_env)
    return [head] + [expand_let(child, env) for child in node[1:]]


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert linear SMT problems to JSONL")
    parser.add_argument("--archive", type=Path, required=True, help="Path to linear_smt.zip")
    parser.add_argument("--output", type=Path, required=True, help="Output JSONL path")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(args.archive, "r") as zf:
            zf.extractall(tmpdir)
        smt_files = list(Path(tmpdir).rglob("*.smt2"))

        args.output.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with args.output.open("w", encoding="utf-8") as handle:
            for smt_file in smt_files:
                problem = convert_smt_file(smt_file)
                if problem is None:
                    continue
                handle.write(json.dumps(problem, ensure_ascii=False))
                handle.write("\n")
                written += 1

    print(f"Wrote {written} problems to {args.output}")


if __name__ == "__main__":
    main()
