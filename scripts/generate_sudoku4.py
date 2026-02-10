"""Generate a small 4x4 Sudoku dataset in CEGVR JSONL format.

Variables: v_r_c (r,c in {1..4}), domain 1..4
Constraints: all_different per row/column and 2x2 boxes; givens as equality.
Ground truth: sat (constructed from a known solution).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Tuple


SOLUTION = [
    [1, 2, 3, 4],
    [3, 4, 1, 2],
    [2, 1, 4, 3],
    [4, 3, 2, 1],
]


def var_name(r: int, c: int) -> str:
    return f"v_{r}_{c}"


def base_variables() -> List[dict]:
    vars: List[dict] = []
    for r in range(1, 5):
        for c in range(1, 5):
            vars.append({"name": var_name(r, c), "domain": "int", "bounds": {"lower": 1, "upper": 4}})
    return vars


def structural_constraints() -> List[dict]:
    cons: List[dict] = []
    # rows
    for r in range(1, 5):
        cons.append({"kind": "all_different", "variables": [var_name(r, c) for c in range(1, 5)]})
    # cols
    for c in range(1, 5):
        cons.append({"kind": "all_different", "variables": [var_name(r, c) for r in range(1, 5)]})
    # 2x2 boxes
    for br in (1, 3):
        for bc in (1, 3):
            box = [var_name(r, c) for r in range(br, br + 2) for c in range(bc, bc + 2)]
            cons.append({"kind": "all_different", "variables": box})
    return cons


def given_constraint(r: int, c: int, val: int) -> dict:
    return {
        "kind": "linear_ineq",
        "terms": [{"variable": var_name(r, c), "coefficient": 1}],
        "relation": "=",
        "rhs": float(val),
        "offset": 0.0,
    }


PUZZLES: List[List[Tuple[int, int, int]]] = [
    # Each entry: list of (r, c, val)
    [(1, 1, 1), (2, 2, 4), (3, 3, 4), (4, 4, 1)],
    [(1, 2, 2), (2, 1, 3), (3, 4, 3), (4, 3, 2)],
    [(1, 3, 3), (2, 4, 2), (3, 1, 2), (4, 2, 3)],
    [(1, 4, 4), (2, 3, 1), (3, 2, 1), (4, 1, 4)],
    # Slightly harder: fewer givens
    [(1, 1, 1), (2, 4, 2), (3, 2, 1)],
    [(1, 2, 2), (3, 3, 4), (4, 1, 4)],
]


def build_problem(idx: int, givens: List[Tuple[int, int, int]]) -> dict:
    vars = base_variables()
    cons = structural_constraints()
    for r, c, v in givens:
        cons.append(given_constraint(r, c, v))
    return {
        "problem_id": f"sudoku4-{idx:03d}",
        "task": "scheduling",  # still integer + alldiff constraints
        "variables": vars,
        "constraints": cons,
        "ground_truth": "sat",
        "metadata": {"type": "sudoku4", "givens": givens},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=Path("data/sudoku4/problems.jsonl"))
    args = ap.parse_args()
    out = args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for i, givens in enumerate(PUZZLES, start=1):
            prob = build_problem(i, givens)
            f.write(json.dumps(prob))
            f.write("\n")
    print(f"Wrote {len(PUZZLES)} problems to {out}")


if __name__ == "__main__":
    main()

