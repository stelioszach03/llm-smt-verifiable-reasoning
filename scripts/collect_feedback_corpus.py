"""Collect LLM training pairs from CEGVR run artifacts.

For each problem record, we emit a JSON object with fields:
  - prompt: textual description of variables and constraints
  - feedback: list of UNSAT descriptions seen during the run (if any)
  - target: final model assignment when certified, else empty dict

This corpus can be used for SFT/LoRA where the model learns to map from
problem + solver feedback to better assignments.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


def build_prompt(problem: Dict[str, Any]) -> str:
    variables = problem.get("variables", [])
    constraints = problem.get("constraints", [])
    lines: List[str] = []
    lines.append("You are solving a system of linear constraints.")
    lines.append("Provide numeric assignments for each variable.")
    lines.append("")
    lines.append("Variables:")
    for v in variables:
        name = v.get("name")
        b = v.get("bounds", {})
        lines.append(f"- {name} in [{b.get('lower','-inf')}, {b.get('upper','inf')}]")
    lines.append("")
    lines.append("Constraints:")
    for c in constraints:
        if c.get("kind") == "linear_ineq":
            parts = [f"({t['coefficient']})*{t['variable']}" for t in c.get("terms", [])]
            lhs = " + ".join(parts) if parts else "0"
            lines.append(f"- {lhs} {c.get('relation')} {c.get('rhs')}")
        elif c.get("kind") == "all_different":
            lines.append(f"- all_different({', '.join(c.get('variables', []))})")
        elif c.get("kind") == "int_domain":
            lines.append(f"- {c.get('lower')} <= {c.get('variable')} <= {c.get('upper')}")
    return "\n".join(lines)


def iter_records(paths: Iterable[Path]) -> Iterable[Dict[str, Any]]:
    for path in paths:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)


def main() -> None:
    ap = argparse.ArgumentParser(description="Collect feedback corpus from runs")
    ap.add_argument("--runs", type=Path, required=True, help="Directory with seed_*.jsonl")
    ap.add_argument("--problems", type=Path, required=False, help="Original problems JSONL (optional)")
    ap.add_argument("--out", type=Path, required=True, help="Output JSONL path")
    args = ap.parse_args()

    run_files = sorted(args.runs.glob("seed_*.jsonl"))
    out = args.out
    out.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with out.open("w", encoding="utf-8") as sink:
        for rec in iter_records(run_files):
            history = rec.get("history", [])
            problem = rec.get("trace") or {}  # when certified it contains the problem structure
            if not problem:
                # fallback: try to reconstruct from fields if present
                problem = {
                    "problem_id": rec.get("problem_id"),
                    "task": rec.get("task", "math"),
                }
            feedback_lines: List[str] = []
            for h in history:
                if isinstance(h, dict) and h.get("status") == "unsat":
                    solver = h.get("solver") or {}
                    descs = solver.get("unsat_descriptions") or []
                    for d in descs[:8]:
                        feedback_lines.append(str(d))
            item = {
                "problem_id": rec.get("problem_id"),
                "prompt": build_prompt(problem),
                "feedback": feedback_lines,
                "target": rec.get("model", {}),
                "status": rec.get("status"),
            }
            sink.write(json.dumps(item))
            sink.write("\n")
            written += 1
    print(f"Wrote {written} training items to {out}")


if __name__ == "__main__":  # pragma: no cover
    main()

