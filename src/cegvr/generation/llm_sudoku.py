"""LLM-backed generator for 4x4 Sudoku (alldifferent constraints)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List

import requests  # type: ignore[import-untyped]

from .provider import TraceGenerator


@dataclass
class LLMSudoku4Generator(TraceGenerator):
    endpoint: str = "http://127.0.0.1:8000/v1/chat/completions"
    model: str = "llama-3-8b-instruct"
    temperature: float = 0.2
    max_tokens: int = 256

    def propose(
        self, problem: dict, budget: int, hint: dict | None = None
    ) -> list[dict]:
        if budget <= 0:
            return []
        attempts: List[dict] = []
        for _ in range(budget):
            payload = self._build_payload(problem, hint)
            try:
                resp = requests.post(self.endpoint, json=payload, timeout=30)
                resp.raise_for_status()
            except requests.RequestException:
                continue
            assignment = self._parse_response(resp.json())
            if assignment is None:
                continue
            attempts.append(self._build_trace(problem, assignment))
        return attempts

    def _build_payload(self, problem: dict, hint: dict | None = None) -> dict:
        givens = []
        for c in problem.get("constraints", []):
            if c.get("kind") == "linear_ineq" and c.get("relation") == "=":
                terms = c.get("terms", [])
                if len(terms) == 1:
                    givens.append((terms[0]["variable"], c.get("rhs")))
        grid = [["." for _ in range(4)] for _ in range(4)]
        for var, val in givens:
            try:
                _, r, c = var.split("_")
                rr, cc = int(r) - 1, int(c) - 1
                grid[rr][cc] = str(int(val))
            except Exception:
                continue
        lines = ["Fill the 4x4 Sudoku. Use digits 1..4."]
        lines.append('Return JSON: {"assignments": {"v_r_c": int, ...}} only.')
        lines.append("Grid (rows top-down), '.' are blanks:")
        for r in range(4):
            lines.append(" ".join(grid[r]))
        feedback_lines: list[str] = []
        if hint and isinstance(hint, dict):
            issues = hint.get("issues")
            if isinstance(issues, list):
                for issue in issues:
                    if isinstance(issue, dict) and issue.get("type") == "unsat_core":
                        descs = (
                            issue.get("unsat_descriptions")
                            or issue.get("unsat_core")
                            or []
                        )
                        for d in descs[:8]:
                            feedback_lines.append(str(d))
        # try to include previous assignment to enable targeted revision
        prev_assign: dict[str, int] | None = None
        if hint and isinstance(hint, dict):
            issues = hint.get("issues")
            if isinstance(issues, list):
                for issue in issues:
                    la = (
                        issue.get("last_assignment")
                        if isinstance(issue, dict)
                        else None
                    )
                    if isinstance(la, dict) and la:
                        prev_assign = la
                        break
        if prev_assign:
            lines.append("")
            lines.append("Previous attempt (revise only the conflicting cells):")
            prev_grid = [["." for _ in range(4)] for _ in range(4)]
            for k, v in prev_assign.items():
                if not isinstance(v, int):
                    continue
                try:
                    _, r, c = k.split("_")
                    rr, cc = int(r) - 1, int(c) - 1
                    prev_grid[rr][cc] = str(v)
                except Exception:
                    continue
            for r in range(4):
                lines.append(" ".join(prev_grid[r]))
        if feedback_lines:
            lines.append("")
            lines.append("Solver feedback (conflicting constraints):")
            for d in feedback_lines:
                lines.append(f"- {d}")
        messages = [
            {"role": "system", "content": "You return valid JSON only."},
            {"role": "user", "content": "\n".join(lines)},
        ]
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }

    def _parse_response(self, payload: dict) -> dict | None:
        try:
            content = payload["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError):
            return None
        content = content.split("```json", 1)[-1] if "```json" in content else content
        content = content.split("```", 1)[0]
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return None
        assignments = data.get("assignments")
        if not isinstance(assignments, dict):
            return None
        parsed: Dict[str, int] = {}
        for k, v in assignments.items():
            try:
                parsed[str(k)] = int(v)
            except Exception:
                return None
        return parsed

    def _build_trace(self, problem: dict, assignment: Dict[str, int]) -> dict:
        steps: List[dict] = []
        for i, (var, val) in enumerate(assignment.items(), start=1):
            steps.append(
                {
                    "id": i,
                    "kind": "derive",
                    "expr": {
                        "type": "binary",
                        "op": "=",
                        "left": {"type": "variable", "name": var},
                        "right": {"type": "constant", "value": val},
                    },
                    "note": "LLM suggested assignment",
                }
            )
        trace = {
            "problem_id": problem.get("problem_id", "sudoku4-llm"),
            "task": problem.get("task", "scheduling"),
            "variables": problem.get("variables", []),
            "assumptions": [],
            "steps": steps,
            "constraints": problem.get("constraints", []),
            "objective": {"type": "value"},
            "answer": {"value": assignment, "justification": "LLM-proposed assignment"},
        }
        return trace


__all__ = ["LLMSudoku4Generator"]
