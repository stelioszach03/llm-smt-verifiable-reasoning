"""Generate a small 5x5 Latin square dataset (row/column all_different)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Tuple


SOLUTION = [
    [1, 2, 3, 4, 5],
    [2, 3, 4, 5, 1],
    [3, 4, 5, 1, 2],
    [4, 5, 1, 2, 3],
    [5, 1, 2, 3, 4],
]


def var_name(r: int, c: int) -> str:
    return f"v_{r}_{c}"


def variables() -> List[dict]:
    return [
        {"name": var_name(r, c), "domain": "int", "bounds": {"lower": 1, "upper": 5}}
        for r in range(1, 6) for c in range(1, 6)
    ]


def constraints() -> List[dict]:
    cons: List[dict] = []
    for r in range(1, 6):
        cons.append({"kind": "all_different", "variables": [var_name(r, c) for c in range(1, 6)]})
    for c in range(1, 6):
        cons.append({"kind": "all_different", "variables": [var_name(r, c) for r in range(1, 6)]})
    return cons


PUZZLES: List[List[Tuple[int, int, int]]] = [
    # four givens
    [(1, 1, 1), (2, 2, 3), (3, 3, 5), (4, 4, 2)],
    [(1, 2, 2), (2, 3, 4), (3, 4, 1), (5, 5, 4)],
    # three givens (harder)
    [(1, 5, 5), (3, 2, 4), (5, 3, 2)],
    [(2, 1, 2), (4, 5, 3), (5, 4, 3)],
]


def given_constraint(r: int, c: int, val: int) -> dict:
    return {
        "kind": "linear_ineq",
        "terms": [{"variable": var_name(r, c), "coefficient": 1}],
        "relation": "=",
        "rhs": float(val),
        "offset": 0.0,
    }


def build_problem(idx: int, givens: List[Tuple[int, int, int]]) -> dict:
    cons = constraints()
    for r, c, v in givens:
        cons.append(given_constraint(r, c, v))
    return {
        "problem_id": f"latin5-{idx:03d}",
        "task": "scheduling",
        "variables": variables(),
        "constraints": cons,
        "ground_truth": "sat",
        "metadata": {"type": "latin5", "givens": givens},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=Path("data/latin5/problems.jsonl"))
    args = ap.parse_args()
    out = args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for i, givens in enumerate(PUZZLES, start=1):
            p = build_problem(i, givens)
            f.write(json.dumps(p))
            f.write("\n")
    print(f"Wrote {len(PUZZLES)} problems to {out}")


if __name__ == "__main__":
    main()

