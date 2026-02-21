"""Tests for the candidate-first LLM generator."""

from __future__ import annotations

from cegvr.generation.llm_candidate_linear import LLMLinearCandidateGenerator


def test_parse_response_falls_back_to_reasoning_content() -> None:
    generator = LLMLinearCandidateGenerator()
    payload = {
        "choices": [
            {
                "message": {
                    "content": "",
                    "reasoning_content": (
                        '{"status":"sat","assignment":{"x0":2,"x1":1}}'
                    ),
                }
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 12,
            "total_tokens": 22,
        },
    }

    proposal = generator._parse_response(payload, elapsed_ms=123.0)

    assert proposal.candidate is not None
    assert proposal.candidate.status == "sat"
    assert proposal.candidate.assignment == {"x0": 2, "x1": 1}
    assert proposal.prompt_tokens == 10
    assert proposal.completion_tokens == 12
    assert proposal.total_tokens == 22
