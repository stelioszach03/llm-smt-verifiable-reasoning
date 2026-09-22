"""LLM-backed generator for linear feasibility problems."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Dict, List

import requests  # type: ignore[import-untyped]

from .provider import TraceGenerator


@dataclass
class LLMLinearGenerator(TraceGenerator):
    """Generator that queries a local LLM server for candidate assignments."""

    endpoint: str = "http://127.0.0.1:8000/v1/chat/completions"
    model: str = "qwen3.5-35b-a3b"
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
                response = requests.post(self.endpoint, json=payload, timeout=30)
                response.raise_for_status()
                response_payload = response.json()
            except (requests.RequestException, ValueError):
                continue
            assignment = self._parse_response(response_payload)
            if assignment is None:
                continue
            attempts.append(self._build_trace(problem, assignment))
        return attempts

    def _build_payload(self, problem: dict, hint: dict | None = None) -> dict:
        variables = problem.get("variables", [])
        constraints = problem.get("constraints", [])
        description = [
            "You are solving a system of linear inequalities.",
            "Provide values for each variable that satisfy all constraints.",
            "Respond with a JSON object under the key 'assignments' where each"
            " key is the variable name and each value is a number.",
            "If you believe the system is infeasible, respond with {'assignments': {}}.",
        ]
        var_lines = [
            f"- {var['name']}: domain {var.get('domain', 'real')}"
            f" in [{var.get('bounds', {}).get('lower', '-inf')},"
            f" {var.get('bounds', {}).get('upper', 'inf')}]."
            for var in variables
        ]
        constraint_lines = []
        for constraint in constraints:
            if constraint.get("kind") != "linear_ineq":
                continue
            lhs_terms = (
                " + ".join(
                    f"({term['coefficient']})*{term['variable']}"
                    for term in constraint.get("terms", [])
                )
                or "0"
            )
            constraint_lines.append(
                f"{lhs_terms} {constraint['relation']} {constraint['rhs']}"
            )

        feedback_lines: list[str] = []
        if hint and isinstance(hint, dict):
            issues = hint.get("issues")
            if isinstance(issues, list):
                unsat_texts: list[str] = []
                for issue in issues:
                    if not isinstance(issue, dict):
                        continue
                    if issue.get("type") == "unsat_core":
                        if issue.get("unsat_descriptions"):
                            unsat_texts.extend(
                                [str(s) for s in issue["unsat_descriptions"]]
                            )
                        elif issue.get("unsat_core"):
                            unsat_texts.extend([str(s) for s in issue["unsat_core"]])
                if unsat_texts:
                    feedback_lines.append(
                        "Previous attempt was UNSAT. Consider these conflicting constraints:"
                    )
                    # limit to a few lines to keep prompt compact
                    for line in unsat_texts[:8]:
                        feedback_lines.append(f"- {line}")
                    feedback_lines.append(
                        "Revise assignments to satisfy all the above simultaneously, or return an empty 'assignments' if impossible."
                    )

        prompt = "\n".join(
            description
            + (["", "Solver feedback:"] + feedback_lines if feedback_lines else [])
            + ["", "Variables:"]
            + var_lines
            + ["", "Constraints:"]
            + constraint_lines
        )
        messages = [
            {"role": "system", "content": "You return valid JSON only."},
            {"role": "user", "content": prompt},
        ]
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }

    def _parse_response(self, payload: dict) -> dict | None:
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return None
        if not isinstance(content, str):
            return None
        content = content.strip()
        content = content.split("```json", 1)[-1] if "```json" in content else content
        content = content.split("```", 1)[0]
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        assignments = data.get("assignments")
        if not isinstance(assignments, dict):
            return None
        parsed: Dict[str, float] = {}
        for key, value in assignments.items():
            try:
                number = float(value)
                if isinstance(value, bool) or not math.isfinite(number):
                    return None
                parsed[key] = number
            except (TypeError, ValueError):
                return None
        return parsed

    def _build_trace(self, problem: dict, assignment: Dict[str, float]) -> dict:
        steps: List[dict] = []
        for idx, (var, value) in enumerate(assignment.items(), start=1):
            steps.append(
                {
                    "id": idx,
                    "kind": "derive",
                    "expr": {
                        "type": "binary",
                        "op": "=",
                        "left": {"type": "variable", "name": var},
                        "right": {"type": "constant", "value": value},
                    },
                    "note": "LLM suggested assignment",
                }
            )

        trace = {
            "problem_id": problem.get("problem_id", "linear-llm"),
            "task": problem.get("task", "math"),
            "variables": problem.get("variables", []),
            "assumptions": [],
            "steps": steps,
            "constraints": problem.get("constraints", []),
            "objective": {"type": "value"},
            "answer": {
                "value": assignment,
                "justification": "LLM-proposed assignment",
            },
        }
        return trace


__all__ = ["LLMLinearGenerator"]
