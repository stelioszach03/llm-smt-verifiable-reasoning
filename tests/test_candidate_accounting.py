"""Generation accounting and solver-witness information boundaries."""

import copy
import json

import pytest

from cegvr.candidate.repair import repair_candidates_until_certified
from cegvr.candidate.types import CandidateOutput, CandidateProposal, ExperimentArm
from cegvr.generation.llm_candidate_linear import LLMLinearCandidateGenerator


PROBLEM = {
    "problem_id": "audit-accounting",
    "task": "math",
    "ground_truth": "sat",
    "variables": [{"name": "x", "domain": "int", "bounds": {"lower": 0, "upper": 5}}],
    "constraints": [
        {
            "constraint_id": "c1",
            "kind": "linear_ineq",
            "terms": [{"variable": "x", "coefficient": 1}],
            "relation": "=",
            "rhs": 2,
        }
    ],
}


def proposal(candidate, index=0):
    return CandidateProposal(
        candidate=candidate,
        raw_content=json.dumps(candidate.model_dump()),
        raw_payload=None,
        llm_latency_ms=index + 1,
        prompt_tokens=10 + index,
        completion_tokens=20 + index,
        total_tokens=30 + 2 * index,
    )


class Batch:
    def propose_candidates(self, problem, budget, hint=None):
        self.generated = [
            proposal(
                CandidateOutput(status="sat", assignment={"x": 2 if i == 0 else 0}), i
            )
            for i in range(budget)
        ]
        return self.generated


def test_eager_batch_accounts_all_generations_on_first_candidate_success():
    generator = Batch()
    result = repair_candidates_until_certified(
        PROBLEM,
        generator,
        arm=ExperimentArm.MULTI_NO_FEEDBACK,
        max_rounds=4,
        per_round_budget=4,
    )
    assert result["status"] == "certified"
    assert len(generator.generated) == result["llm_attempts"] == 4
    assert result["prompt_tokens"] == 46
    assert result["completion_tokens"] == 86
    assert result["total_tokens"] == 132
    assert result["llm_latency_ms"] == 10
    assert result["evaluated_candidates"] == 1
    assert result["unevaluated_candidates"] == 3
    assert len(result["generated_candidates"]) == 4
    assert [row["evaluated"] for row in result["generated_candidates"]] == [
        True,
        False,
        False,
        False,
    ]
    assert (
        result["generated_candidates"][3]["raw_candidate"]
        == generator.generated[3].raw_content
    )
    assert len(result["history"]) == result["solver_calls"] == 1


def test_unknown_usage_is_not_zero_and_known_subtotal_is_retained():
    class UnknownBatch(Batch):
        def propose_candidates(self, problem, budget, hint=None):
            rows = super().propose_candidates(problem, budget, hint)
            rows[-1].prompt_tokens = rows[-1].completion_tokens = rows[
                -1
            ].total_tokens = None
            return rows

    result = repair_candidates_until_certified(
        PROBLEM,
        UnknownBatch(),
        arm=ExperimentArm.MULTI_NO_FEEDBACK,
        max_rounds=1,
        per_round_budget=4,
    )
    assert (
        result["prompt_tokens"]
        is result["completion_tokens"]
        is result["total_tokens"]
        is None
    )
    assert result["known_total_tokens"] == 96
    assert result["usage_complete"] is False
    assert result["usage_measurements"]["total_tokens"] == 3


@pytest.mark.parametrize(
    "arm", [ExperimentArm.MULTI_UNSAT_CORE_FEEDBACK, ExperimentArm.CD_VGS_CORE_RANK]
)
@pytest.mark.parametrize("policy,expected", [("include", True), ("withhold", False)])
def test_false_unsat_witness_policy_is_explicit_in_prompt(arm, policy, expected):
    class Recorder:
        def __init__(self):
            self.hints = []

        def propose_candidates(self, problem, budget, hint=None):
            self.hints.append(copy.deepcopy(hint))
            candidate = (
                CandidateOutput(status="unsat")
                if hint is None
                else CandidateOutput(status="sat", assignment={"x": 2})
            )
            return [proposal(candidate)]

    generator = Recorder()
    result = repair_candidates_until_certified(
        PROBLEM,
        generator,
        arm=arm,
        max_rounds=2,
        per_round_budget=1,
        witness_policy=policy,
    )
    hint = generator.hints[1]
    assert (hint.sat_witness is not None) is expected
    prompt = LLMLinearCandidateGenerator()._build_prompt(PROBLEM, hint)
    assert ("  x = 2" in prompt) is expected
    assert result["witness_policy"] == policy


def test_withhold_diagnostics_come_only_from_candidate_not_verifier(monkeypatch):
    import cegvr.candidate.repair as repair

    actual = repair.verify_linear_candidate

    def poisoned(problem, candidate, **kwargs):
        result = actual(problem, candidate, **kwargs)
        if result.failure_type == "false_unsat_claim":
            result.diagnostics = {
                "last_assignment": {"x": 2},
                "solver_witness": {"x": 2},
                "nested": {"answer": 2},
            }
        return result

    monkeypatch.setattr(repair, "verify_linear_candidate", poisoned)

    class Recorder:
        def __init__(self):
            self.hints = []

        def propose_candidates(self, problem, budget, hint=None):
            self.hints.append(copy.deepcopy(hint))
            return [proposal(CandidateOutput(status="unsat"))]

    generator = Recorder()
    repair_candidates_until_certified(
        PROBLEM,
        generator,
        arm=ExperimentArm.MULTI_UNSAT_CORE_FEEDBACK,
        max_rounds=2,
        per_round_budget=1,
        witness_policy="withhold",
    )
    hint = generator.hints[1]
    assert hint.sat_witness is None
    assert not hint.diagnostics.get("last_assignment")
    assert "solver_witness" not in hint.diagnostics and "nested" not in hint.diagnostics
