"""Candidate-first LLM generator for linear and small CSP assignments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from time import perf_counter

from pydantic import ValidationError as PydanticValidationError
import requests  # type: ignore[import-untyped]

from cegvr.candidate.types import (
    CandidateOutput,
    CandidateProposal,
    VerifierFeedback,
    candidate_output_schema,
)
from cegvr.generation.json_guard import strip_code_fences
from cegvr.generation.provider import CandidateGenerator


@dataclass
class LLMLinearCandidateGenerator(CandidateGenerator):
    """Query an OpenAI-compatible local endpoint for candidate outputs."""

    endpoint: str = "http://127.0.0.1:8000/v1/chat/completions"
    model: str = "qwen3.5-35b-a3b"
    temperature: float = 0.2
    max_tokens: int = 256
    enable_thinking: bool = False
    context_cap: int = 8192

    def propose_candidates(
        self,
        problem: dict,
        budget: int,
        hint: VerifierFeedback | None = None,
    ) -> list[CandidateProposal]:
        if budget <= 0:
            return []

        proposals: list[CandidateProposal] = []
        for _ in range(budget):
            payload = self._build_payload(problem, hint)
            start = perf_counter()
            try:
                response = requests.post(self.endpoint, json=payload, timeout=60)
                response.raise_for_status()
                elapsed_ms = (perf_counter() - start) * 1000.0
                body = response.json()
            except (requests.RequestException, ValueError):
                proposals.append(
                    CandidateProposal(
                        candidate=None,
                        raw_content=None,
                        raw_payload=None,
                        llm_latency_ms=(perf_counter() - start) * 1000.0,
                    )
                )
                continue
            proposals.append(self._parse_response(body, elapsed_ms))
        return proposals

    def _build_payload(
        self, problem: dict, hint: VerifierFeedback | None = None
    ) -> dict:
        messages = [
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user", "content": self._build_prompt(problem, hint)},
        ]
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "candidate_output",
                    "schema": candidate_output_schema(),
                },
            },
            "chat_template_kwargs": {"enable_thinking": self.enable_thinking},
        }

    def _build_prompt(self, problem: dict, hint: VerifierFeedback | None) -> str:
        lines: list[str] = []
        lines.append("Solve the constraint problem.")
        lines.append("Return a JSON object with status='sat' and a full assignment,")
        lines.append("or status='unsat' if no satisfying assignment exists.")
        lines.append("Do not include explanations outside JSON.")
        lines.append("")
        lines.append("Variables:")
        for variable in problem.get("variables", []):
            bounds = variable.get("bounds") or {}
            lines.append(
                f"- {variable['name']}: {variable.get('domain', 'int')} "
                f"in [{bounds.get('lower', '-inf')}, {bounds.get('upper', 'inf')}]"
            )
        lines.append("")
        lines.append("Constraints:")
        for constraint in problem.get("constraints", []):
            lines.append(f"- {self._describe_constraint(constraint)}")

        if hint is not None:
            lines.append("")
            lines.append("Previous round feedback:")
            if hint.generic_feedback:
                lines.append(f"- {hint.generic_feedback}")
            if hint.variables_to_revise:
                lines.append("- Revise first: " + ", ".join(hint.variables_to_revise))
            if hint.variables_to_keep_fixed:
                lines.append(
                    "- Keep fixed if possible: "
                    + ", ".join(hint.variables_to_keep_fixed)
                )
            conflict_refs = hint.conflict_constraints or hint.unsat_core
            if conflict_refs:
                for item in conflict_refs:
                    lines.append(f"- Conflict: {item.constraint_text}")
            if hint.sat_witness:
                lines.append("- A solver witness exists. Prefer a satisfying assignment.")
                for key, value in sorted(hint.sat_witness.items()):
                    lines.append(f"  {key} = {value}")
            diagnostics = hint.diagnostics or {}
            last_assignment = diagnostics.get("last_assignment")
            if isinstance(last_assignment, dict) and last_assignment:
                lines.append("- Previous assignment:")
                for key, value in sorted(last_assignment.items()):
                    lines.append(f"  {key} = {value}")

        lines.append("")
        lines.append("Return JSON only.")
        return "\n".join(lines)

    def _parse_response(self, payload: dict, elapsed_ms: float) -> CandidateProposal:
        try:
            message = payload["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            return CandidateProposal(
                candidate=None,
                raw_content=None,
                raw_payload=payload,
                llm_latency_ms=elapsed_ms,
            )

        content = None
        if isinstance(message, dict):
            primary = message.get("content")
            if isinstance(primary, str) and primary.strip():
                content = primary
            else:
                fallback = message.get("reasoning_content")
                if isinstance(fallback, str) and fallback.strip():
                    content = fallback

        cleaned = strip_code_fences(str(content or "").strip())
        try:
            raw_candidate = json.loads(cleaned)
            candidate = CandidateOutput.model_validate(raw_candidate)
        except (json.JSONDecodeError, PydanticValidationError, ValueError):
            candidate = None

        usage = payload.get("usage") if isinstance(payload, dict) else None
        prompt_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
        completion_tokens = (
            usage.get("completion_tokens") if isinstance(usage, dict) else None
        )
        total_tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
        timings = payload.get("timings") if isinstance(payload, dict) else None
        llm_latency_ms = elapsed_ms
        if isinstance(timings, dict):
            prompt_ms = timings.get("prompt_ms") or 0.0
            predicted_ms = timings.get("predicted_ms") or timings.get("total_ms") or 0.0
            llm_latency_ms = float(prompt_ms) + float(predicted_ms)

        return CandidateProposal(
            candidate=candidate,
            raw_content=cleaned,
            raw_payload=payload,
            llm_latency_ms=llm_latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _describe_constraint(constraint: dict) -> str:
        kind = constraint.get("kind")
        if kind == "linear_ineq":
            terms = " + ".join(
                f"({term['coefficient']})*{term['variable']}"
                for term in constraint.get("terms", [])
            ) or "0"
            offset = constraint.get("offset", 0.0)
            if offset:
                terms = f"{terms} + {offset}"
            return f"{terms} {constraint.get('relation')} {constraint.get('rhs')}"
        if kind == "all_different":
            return "all_different(" + ", ".join(constraint.get("variables", [])) + ")"
        if kind == "int_domain":
            return (
                f"{constraint.get('lower')} <= {constraint.get('variable')} "
                f"<= {constraint.get('upper')}"
            )
        if kind == "bool_atom":
            return f"{constraint.get('variable')} == {constraint.get('value')}"
        return json.dumps(constraint, sort_keys=True)


__all__ = ["LLMLinearCandidateGenerator"]
