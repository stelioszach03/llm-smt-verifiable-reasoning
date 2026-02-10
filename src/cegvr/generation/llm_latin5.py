"""LLM-backed generator for 5x5 Latin square (rows/cols all different)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List

import requests  # type: ignore[import-untyped]

from .provider import TraceGenerator


@dataclass
class LLMLatin5Generator(TraceGenerator):
    endpoint: str = "http://127.0.0.1:8000/v1/chat/completions"
    model: str = "llama-3-8b-instruct"
    temperature: float = 0.2
    max_tokens: int = 512

    def propose(
        self, problem: dict, budget: int, hint: dict | None = None
    ) -> list[dict]:
        if budget <= 0:
            return []
        out: List[dict] = []
        for _ in range(budget):
            payload = self._build_payload(problem, hint)
            try:
                r = requests.post(self.endpoint, json=payload, timeout=45)
                r.raise_for_status()
            except requests.RequestException:
                continue
            assignment = self._parse_response(r.json())
            if assignment is None:
                continue
            out.append(self._build_trace(problem, assignment))
        return out

    def _build_payload(self, problem: dict, hint: dict | None = None) -> dict:
        # reconstruct givens
        givens: list[tuple[str, int]] = []
        for c in problem.get("constraints", []):
            if c.get("kind") == "linear_ineq" and c.get("relation") == "=":
                t = c.get("terms", [])
                if len(t) == 1:
                    try:
                        givens.append((t[0]["variable"], int(c.get("rhs"))))
                    except Exception:
                        pass
        grid = [["." for _ in range(5)] for _ in range(5)]
        for var, val in givens:
            try:
                _, rs, cs = var.split("_")
                rr, cc = int(rs) - 1, int(cs) - 1
                grid[rr][cc] = str(val)
            except Exception:
                continue
        lines = ["Fill the 5x5 Latin square with digits 1..5."]
        lines.append("Rows and columns must contain all digits without repetition.")
        lines.append('Return JSON only: {"assignments": {"v_r_c": int, ...}}.')
        lines.append("Grid ('.' is blank):")
        for r in range(5):
            lines.append(" ".join(grid[r]))
        # include previous attempt and solver feedback if present
        prev: dict[str, int] | None = None
        fb: list[str] = []
        if hint and isinstance(hint, dict):
            issues = hint.get("issues")
            if isinstance(issues, list):
                for issue in issues:
                    if isinstance(issue, dict):
                        if not prev and isinstance(issue.get("last_assignment"), dict):
                            prev = issue.get("last_assignment")
                        descs = (
                            issue.get("unsat_descriptions")
                            or issue.get("unsat_core")
                            or []
                        )
                        for d in descs[:8]:
                            fb.append(str(d))
        if prev:
            lines.append("")
            lines.append("Previous attempt (revise only conflicting cells):")
            pgrid = [["." for _ in range(5)] for _ in range(5)]
            for k, v in prev.items():
                if not isinstance(v, int):
                    continue
                try:
                    _, rs, cs = k.split("_")
                    rr, cc = int(rs) - 1, int(cs) - 1
                    pgrid[rr][cc] = str(v)
                except Exception:
                    continue
            for r in range(5):
                lines.append(" ".join(pgrid[r]))
        if fb:
            lines.append("")
            lines.append("Solver feedback (conflicts):")
            for d in fb:
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
        a = data.get("assignments")
        parsed: Dict[str, int] = {}
        if isinstance(a, dict):
            for k, v in a.items():
                try:
                    parsed[str(k)] = int(v)
                except Exception:
                    return None
        else:
            # fallback: accept grid format [[...], ...]
            grid = data.get("grid")
            if isinstance(grid, list) and len(grid) == 5:
                try:
                    for r in range(5):
                        row = grid[r]
                        if not isinstance(row, list) or len(row) != 5:
                            return None
                        for c in range(5):
                            val = int(row[c])
                            parsed[f"v_{r + 1}_{c + 1}"] = val
                except Exception:
                    return None
            else:
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
        return {
            "problem_id": problem.get("problem_id", "latin5-llm"),
            "task": problem.get("task", "scheduling"),
            "variables": problem.get("variables", []),
            "assumptions": [],
            "steps": steps,
            "constraints": problem.get("constraints", []),
            "objective": {"type": "value"},
            "answer": {"value": assignment, "justification": "LLM-proposed assignment"},
        }


__all__ = ["LLMLatin5Generator"]
