"""Export case studies for appendix sections."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from cegvr.data.loader import iter_jsonl_problems
from cegvr.eval.aggregate import load_run


def _index_problems(problems_path: Path | str) -> Dict[str, dict]:
    mapping: Dict[str, dict] = {}
    for problem in iter_jsonl_problems(problems_path):
        pid = str(problem.get("problem_id"))
        mapping[pid] = problem
    return mapping


def _load_results(run_dir: Path | str) -> List[dict]:
    run_dir = Path(run_dir)
    records: List[dict] = []
    for path in sorted(run_dir.glob("seed_*.jsonl")):
        records.extend(load_run(path))
    return records


def _select_cases(
    records: List[dict], problems: Dict[str, dict], n: int
) -> Tuple[List[dict], List[dict]]:
    sat_cases: List[dict] = []
    unsat_cases: List[dict] = []
    for record in records:
        pid = str(record.get("problem_id"))
        problem = problems.get(pid)
        if not problem:
            continue
        truth = problem.get("ground_truth")
        if (
            record.get("status") == "certified"
            and truth == "sat"
            and len(sat_cases) < n
        ):
            sat_cases.append({**record, "problem": problem})
        elif (
            record.get("status") != "certified"
            and truth == "unsat"
            and len(unsat_cases) < n
        ):
            unsat_cases.append({**record, "problem": problem})
        if len(sat_cases) >= n and len(unsat_cases) >= n:
            break
    return sat_cases, unsat_cases


def _format_problem(problem: dict) -> str:
    return json.dumps(problem, indent=2, sort_keys=True)


def _format_trace(record: dict) -> str:
    trace = record.get("trace")
    if trace is None:
        return "_No certified trace available._"
    return json.dumps(trace, indent=2, sort_keys=True)


def _format_solver_summary(record: dict) -> str:
    model = record.get("model")
    if model:
        pretty_model = json.dumps(model, indent=2, sort_keys=True)
    else:
        pretty_model = "_No model available._"
    iterations = record.get("iterations", "N/A")
    latency = record.get("latency_ms", "N/A")
    solver_calls = record.get("solver_calls", "N/A")
    return (
        f"- Iterations: {iterations}\n"
        f"- Latency (ms): {latency}\n"
        f"- Solver calls: {solver_calls}\n"
        f"- Model:\n\n```json\n{pretty_model}\n```"
    )


def _format_unsat_core(record: dict) -> str:
    feedback = record.get("feedback") or {}
    issues = feedback.get("issues") if isinstance(feedback, dict) else None
    unsat_core = []
    if issues:
        for issue in issues:
            if issue.get("type") == "unsat_core":
                unsat_core.extend(issue.get("unsat_core", []))
    if unsat_core:
        joined = "\n".join(f"- {item}" for item in unsat_core)
        return f"Unsat core traces:\n{joined}"
    if record.get("status") != "certified":
        solver_info = record.get("history", [])
        core_entries = []
        for entry in solver_info:
            solver_payload = entry.get("solver")
            if (
                isinstance(solver_payload, dict)
                and solver_payload.get("status") == "unsat"
            ):
                core_entries = solver_payload.get("unsat_core", [])
                break
        if core_entries:
            joined = "\n".join(f"- {item}" for item in core_entries)
            return f"Unsat core traces:\n{joined}"
    return "_No unsat-core diagnostics available._"


def export_case_studies(
    *,
    run_dir: Path | str,
    problems_path: Path | str,
    output_path: Path | str,
    n: int = 3,
) -> None:
    """Export SAT and UNSAT case studies to a Markdown file."""

    records = _load_results(run_dir)
    problems = _index_problems(problems_path)
    sat_cases, unsat_cases = _select_cases(records, problems, n)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = ["# Case Studies", ""]

    def append_case(section_title: str, cases: Iterable[dict]) -> None:
        lines.append(f"## {section_title}")
        lines.append("")
        found = False
        for record in cases:
            found = True
            pid = record.get("problem_id")
            lines.append(f"### Problem `{pid}`")
            lines.append("")
            lines.append("**Problem Specification**")
            lines.append("")
            lines.append("```json")
            lines.append(_format_problem(record["problem"]))
            lines.append("```")
            lines.append("")
            lines.append("**Certified Trace**")
            lines.append("")
            lines.append("```json")
            lines.append(_format_trace(record))
            lines.append("```")
            lines.append("")
            lines.append("**Solver Summary**")
            lines.append("")
            lines.append(_format_solver_summary(record))
            lines.append("")
            lines.append("**Unsat-Core Diagnostics**")
            lines.append("")
            lines.append(_format_unsat_core(record))
            lines.append("")
        if not found:
            lines.append("_No matching cases available._")
            lines.append("")

    append_case("Certified SAT Cases", sat_cases)
    append_case("UNSAT Cases", unsat_cases)

    output.write_text("\n".join(lines), encoding="utf-8")


__all__ = ["export_case_studies"]
