"""Convert a subset of MiniZinc scheduling models to CEGVR JSONL.

This converter targets small models using:
  - bounded `var <lower>..<upper>: x;` declarations for integer variables
  - linear inequality constraints using +, -, integer coefficients, and variables
  - `all_different([x, y, z])` constraints

Unsupported constructs (arrays of decision variables, sets, globals beyond
`alldifferent`, reification, etc.) are skipped. Models that cannot be parsed are
ignored. Ground truth labels are computed via Z3 on the translated constraints.
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from z3 import And, Distinct, Int, Optimize, Or, Sum, sat, unsat


VAR_DECL_RE = re.compile(r"var\s+(-?\d+)\s*\.\.\s*(-?\d+)\s*:\s*([A-Za-z_]\w*)\s*;")
VAR_INT_DECL_RE = re.compile(r"var\s+int\s*:\s*([A-Za-z_]\w*)\s*;")
CONSTRAINT_RE = re.compile(r"constraint\s+(.*?)\s*;")
ALLDIFF_RE = re.compile(r"all_different\s*\(\s*\[(.*?)\]\s*\)")


@dataclass
class LinearIneq:
    coeffs: Dict[str, float]
    relation: str
    rhs: float

    def to_cegvr(self) -> dict:
        return {
            "kind": "linear_ineq",
            "terms": [
                {"variable": var, "coefficient": coeff}
                for var, coeff in sorted(self.coeffs.items())
            ],
            "relation": self.relation,
            "rhs": self.rhs,
            "offset": 0.0,
        }


def parse_variables(text: str) -> Dict[str, Tuple[int, int] | None]:
    bounds: Dict[str, Tuple[int, int] | None] = {}
    # bounded declarations
    for m in VAR_DECL_RE.finditer(text):
        lo, hi, name = int(m.group(1)), int(m.group(2)), m.group(3)
        bounds[name] = (lo, hi)
    # unbounded var int: name;
    for m in VAR_INT_DECL_RE.finditer(text):
        name = m.group(1)
        bounds.setdefault(name, None)
    return bounds


def _split_comparator(expr: str) -> Optional[Tuple[str, str, str]]:
    for op in ["<=", ">=", "="]:
        parts = expr.split(op)
        if len(parts) == 2:
            return parts[0].strip(), op, parts[1].strip()
    return None


def _parse_linear_side(side: str) -> Tuple[Dict[str, float], float]:
    # Normalize: replace '-' with '+ -' to split on '+' safely
    s = side.replace("-", "+ -")
    terms = [t.strip() for t in s.split("+") if t.strip()]
    coeffs: Dict[str, float] = {}
    const = 0.0
    for t in terms:
        # Cases: `x`, `2*x`, `-3*y`, numeric constant
        if re.fullmatch(r"-?\d+", t):
            const += float(t)
            continue
        m = re.fullmatch(r"(-?\d+)\s*\*\s*([A-Za-z_]\w*)", t)
        if m:
            c = float(m.group(1))
            v = m.group(2)
            coeffs[v] = coeffs.get(v, 0.0) + c
            continue
        m = re.fullmatch(r"([A-Za-z_]\w*)", t)
        if m:
            v = m.group(1)
            coeffs[v] = coeffs.get(v, 0.0) + 1.0
            continue
        # Unknown term shape → give up on this side
        raise ValueError(f"Unsupported linear term: {t}")
    return coeffs, const


def parse_linear_constraint(expr: str) -> LinearIneq:
    split = _split_comparator(expr)
    if not split:
        raise ValueError("No comparator in expression")
    left, op, right = split
    lcoeffs, lconst = _parse_linear_side(left)
    rcoeffs, rconst = _parse_linear_side(right)
    coeffs = lcoeffs.copy()
    for v, c in rcoeffs.items():
        coeffs[v] = coeffs.get(v, 0.0) - c
    rhs = rconst - lconst
    return LinearIneq(coeffs=coeffs, relation=op, rhs=rhs)


def parse_alldifferent(expr: str) -> Optional[List[str]]:
    m = ALLDIFF_RE.search(expr)
    if not m:
        return None
    raw = m.group(1)
    names = [tok.strip() for tok in raw.split(",") if tok.strip()]
    if not all(re.fullmatch(r"[A-Za-z_]\w*", n) for n in names):
        return None
    return names


def convert_mzn_file(path: Path) -> Optional[dict]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    bounds = parse_variables(text)
    if not bounds:
        return None

    linear_ineqs: List[LinearIneq] = []
    alldiff_sets: List[List[str]] = []
    for m in CONSTRAINT_RE.finditer(text):
        expr = m.group(1)
        names = parse_alldifferent(expr)
        if names:
            alldiff_sets.append(names)
            continue
        try:
            ineq = parse_linear_constraint(expr)
        except Exception:
            continue
        linear_ineqs.append(ineq)

    if not linear_ineqs and not alldiff_sets:
        return None

    # determine all variable names referenced by constraints as well
    referenced: set[str] = set()
    for li in linear_ineqs:
        referenced.update(li.coeffs.keys())
    for group in alldiff_sets:
        referenced.update(group)

    # fill in defaults for unbounded or undeclared variables
    DEFAULT_LO, DEFAULT_HI = -100, 100
    final_bounds: Dict[str, Tuple[int, int]] = {}
    for name, bh in bounds.items():
        if bh is None:
            final_bounds[name] = (DEFAULT_LO, DEFAULT_HI)
        else:
            final_bounds[name] = bh
    for name in referenced:
        final_bounds.setdefault(name, (DEFAULT_LO, DEFAULT_HI))

    variables = [
        {"name": name, "domain": "int", "bounds": {"lower": lo, "upper": hi}}
        for name, (lo, hi) in sorted(final_bounds.items())
    ]
    constraints: List[dict] = []
    for li in linear_ineqs:
        constraints.append(li.to_cegvr())
    for group in alldiff_sets:
        constraints.append({"kind": "all_different", "variables": group})

    # Determine ground truth by asking Z3
    z3_vars = {n: Int(n) for n in final_bounds}
    z3_cons = []
    for n, (lo, hi) in final_bounds.items():
        z3_cons.append(z3_vars[n] >= lo)
        z3_cons.append(z3_vars[n] <= hi)
    for li in linear_ineqs:
        expr = Sum([int(c) * z3_vars[v] for v, c in li.coeffs.items() if v in z3_vars])
        if li.relation == "<=":
            z3_cons.append(expr <= int(li.rhs))
        elif li.relation == ">=":
            z3_cons.append(expr >= int(li.rhs))
        else:
            z3_cons.append(expr == int(li.rhs))
    for group in alldiff_sets:
        z3_cons.append(Distinct(*[z3_vars[v] for v in group if v in z3_vars]))

    opt = Optimize()
    opt.add(z3_cons)
    res = opt.check()
    if res == sat:
        gt = "sat"
    elif res == unsat:
        gt = "unsat"
    else:
        return None

    return {
        "problem_id": f"mzn-{path.stem}",
        "task": "scheduling",
        "variables": variables,
        "constraints": constraints,
        "ground_truth": gt,
        "metadata": {"source": str(path)},
    }


def iter_mzn_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*.mzn"):
        yield p


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert MiniZinc models to CEGVR JSONL (subset)")
    ap.add_argument("--archive", type=Path, required=True, help="Path to scheduling_mzn.zip")
    ap.add_argument("--output", type=Path, required=True, help="Output JSONL path")
    args = ap.parse_args()

    written = 0
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(args.archive, "r") as zf:
            zf.extractall(td)
        out = args.output
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as sink:
            for mzn in iter_mzn_files(Path(td)):
                problem = convert_mzn_file(mzn)
                if problem is None:
                    continue
                sink.write(json.dumps(problem, ensure_ascii=False))
                sink.write("\n")
                written += 1
    print(f"Wrote {written} problems to {args.output}")


if __name__ == "__main__":  # pragma: no cover
    main()
