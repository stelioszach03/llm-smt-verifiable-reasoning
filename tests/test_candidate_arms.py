"""Tests for candidate-pipeline arm isolation."""

from __future__ import annotations

from cegvr.candidate.repair import repair_candidates_until_certified
from cegvr.candidate.types import CandidateOutput, CandidateProposal, ExperimentArm


PROBLEM = {
    "problem_id": "arm-problem",
    "task": "math",
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
    "ground_truth": "sat",
}


PAIR_PROBLEM = {
    "problem_id": "pair-problem",
    "task": "math",
    "variables": [
        {"name": "x", "domain": "int", "bounds": {"lower": 0, "upper": 5}},
        {"name": "y", "domain": "int", "bounds": {"lower": 0, "upper": 5}},
    ],
    "constraints": [
        {
            "constraint_id": "c1",
            "kind": "linear_ineq",
            "terms": [{"variable": "x", "coefficient": 1}],
            "relation": "=",
            "rhs": 2,
        },
        {
            "constraint_id": "c2",
            "kind": "linear_ineq",
            "terms": [{"variable": "y", "coefficient": 1}],
            "relation": "=",
            "rhs": 1,
        },
    ],
    "ground_truth": "sat",
}


class CoreSensitiveGenerator:
    def __init__(self) -> None:
        self.hints = []

    def propose_candidates(self, problem: dict, budget: int, hint=None):
        self.hints.append(hint)
        if hint is not None and hint.unsat_core:
            candidate = CandidateOutput(status="sat", assignment={"x": 2})
        else:
            candidate = CandidateOutput(status="sat", assignment={"x": 0})
        return [
            CandidateProposal(
                candidate=candidate,
                raw_content=None,
                raw_payload=None,
                llm_latency_ms=1.0,
            )
            for _ in range(budget)
        ]


def test_no_feedback_arm_never_carries_solver_feedback() -> None:
    generator = CoreSensitiveGenerator()
    result = repair_candidates_until_certified(
        PROBLEM,
        generator,
        arm=ExperimentArm.MULTI_NO_FEEDBACK,
        max_rounds=2,
        per_round_budget=1,
        timeout_ms=1000,
    )
    assert result["verified_outcome"] == "BUDGET_EXCEEDED"
    assert generator.hints == [None, None]


def test_generic_feedback_arm_redacts_unsat_core() -> None:
    generator = CoreSensitiveGenerator()
    result = repair_candidates_until_certified(
        PROBLEM,
        generator,
        arm=ExperimentArm.MULTI_GENERIC_FEEDBACK,
        max_rounds=2,
        per_round_budget=1,
        timeout_ms=1000,
    )
    assert result["verified_outcome"] == "BUDGET_EXCEEDED"
    assert generator.hints[0] is None
    assert generator.hints[1] is not None
    assert generator.hints[1].generic_feedback is not None
    assert generator.hints[1].unsat_core == []


def test_unsat_core_arm_carries_solver_grounded_feedback() -> None:
    generator = CoreSensitiveGenerator()
    result = repair_candidates_until_certified(
        PROBLEM,
        generator,
        arm=ExperimentArm.MULTI_UNSAT_CORE_FEEDBACK,
        max_rounds=2,
        per_round_budget=1,
        timeout_ms=1000,
    )
    assert result["verified_outcome"] == "CERTIFIED_SAT"
    assert generator.hints[1] is not None
    assert generator.hints[1].unsat_core


class CoreRankParentGenerator:
    def __init__(self) -> None:
        self.hints = []
        self.calls = 0

    def propose_candidates(self, problem: dict, budget: int, hint=None):
        self.hints.append(hint)
        self.calls += 1
        if self.calls == 1:
            return [
                CandidateProposal(
                    candidate=CandidateOutput(
                        status="sat",
                        assignment={"x": 10, "y": 1},
                    ),
                    raw_content=None,
                    raw_payload=None,
                    llm_latency_ms=1.0,
                ),
                CandidateProposal(
                    candidate=CandidateOutput(
                        status="sat",
                        assignment={"x": 0, "y": 1},
                    ),
                    raw_content=None,
                    raw_payload=None,
                    llm_latency_ms=1.0,
                ),
            ]
        return [
            CandidateProposal(
                candidate=CandidateOutput(status="sat", assignment={"x": 2, "y": 1}),
                raw_content=None,
                raw_payload=None,
                llm_latency_ms=1.0,
            )
            for _ in range(budget)
        ]


class DomainRepairGenerator:
    def __init__(self) -> None:
        self.hints = []
        self.calls = 0

    def propose_candidates(self, problem: dict, budget: int, hint=None):
        self.hints.append(hint)
        self.calls += 1
        if self.calls == 1:
            return [
                CandidateProposal(
                    candidate=CandidateOutput(
                        status="sat",
                        assignment={"x": 2, "y": 7, "z": 1},
                    ),
                    raw_content=None,
                    raw_payload=None,
                    llm_latency_ms=1.0,
                )
            ]
        return [
            CandidateProposal(
                candidate=CandidateOutput(status="sat", assignment={"x": 2, "y": 1}),
                raw_content=None,
                raw_payload=None,
                llm_latency_ms=1.0,
            )
        ]


class FalseUnsatRepairGenerator:
    def __init__(self) -> None:
        self.hints = []
        self.calls = 0

    def propose_candidates(self, problem: dict, budget: int, hint=None):
        self.hints.append(hint)
        self.calls += 1
        if self.calls == 1:
            return [
                CandidateProposal(
                    candidate=CandidateOutput(status="unsat"),
                    raw_content=None,
                    raw_payload=None,
                    llm_latency_ms=1.0,
                )
            ]
        return [
            CandidateProposal(
                candidate=CandidateOutput(status="sat", assignment={"x": 2}),
                raw_content=None,
                raw_payload=None,
                llm_latency_ms=1.0,
            )
        ]


class RepeatFailureGenerator:
    def __init__(self) -> None:
        self.hints = []

    def propose_candidates(self, problem: dict, budget: int, hint=None):
        self.hints.append(hint)
        return [
            CandidateProposal(
                candidate=CandidateOutput(status="sat", assignment={"x": 0}),
                raw_content=None,
                raw_payload=None,
                llm_latency_ms=1.0,
            )
        ]


def test_cd_vgs_core_rank_selects_best_failed_parent_and_targets_repair() -> None:
    generator = CoreRankParentGenerator()
    result = repair_candidates_until_certified(
        PAIR_PROBLEM,
        generator,
        arm=ExperimentArm.CD_VGS_CORE_RANK,
        max_rounds=2,
        per_round_budget=2,
        timeout_ms=1000,
    )

    assert result["verified_outcome"] == "CERTIFIED_SAT"
    assert result["search_policy"] == "cd_vgs_core_rank"
    assert result["selected_parent_round_index"] == 1
    assert result["selected_parent_candidate_index"] == 1
    assert generator.hints[1] is not None
    assert generator.hints[1].variables_to_revise == ["x"]
    assert generator.hints[1].variables_to_keep_fixed == ["y"]
    assert generator.hints[1].conflict_constraints
    assert result["llm_attempts"] <= 4


def test_cd_vgs_domain_failure_builds_soft_keep_fixed_packet() -> None:
    generator = DomainRepairGenerator()
    result = repair_candidates_until_certified(
        PAIR_PROBLEM,
        generator,
        arm=ExperimentArm.CD_VGS_CORE_RANK,
        max_rounds=2,
        per_round_budget=1,
        timeout_ms=1000,
    )

    assert result["verified_outcome"] == "CERTIFIED_SAT"
    assert generator.hints[1] is not None
    assert generator.hints[1].variables_to_revise == ["y", "z"]
    assert generator.hints[1].variables_to_keep_fixed == ["x"]
    assert "Keep the fixed set unchanged if possible" in (
        generator.hints[1].generic_feedback or ""
    )


def test_cd_vgs_false_unsat_claim_builds_targeted_sat_instruction() -> None:
    generator = FalseUnsatRepairGenerator()
    result = repair_candidates_until_certified(
        PROBLEM,
        generator,
        arm=ExperimentArm.CD_VGS_CORE_RANK,
        max_rounds=2,
        per_round_budget=1,
        timeout_ms=1000,
    )

    assert result["verified_outcome"] == "CERTIFIED_SAT"
    assert generator.hints[1] is not None
    assert generator.hints[1].variables_to_revise == []
    assert generator.hints[1].sat_witness is not None
    assert "satisfiable" in (generator.hints[1].generic_feedback or "")


def test_cd_vgs_repeat_failure_count_tracks_lineage() -> None:
    generator = RepeatFailureGenerator()
    result = repair_candidates_until_certified(
        PROBLEM,
        generator,
        arm=ExperimentArm.CD_VGS_CORE_RANK,
        max_rounds=2,
        per_round_budget=1,
        timeout_ms=1000,
    )

    assert result["verified_outcome"] == "BUDGET_EXCEEDED"
    assert result["repeat_failure_count"] == 1
    assert result["selected_parent_round_index"] == 2
