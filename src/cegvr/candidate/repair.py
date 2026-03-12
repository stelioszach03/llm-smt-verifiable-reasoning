"""Repair loop for the candidate-first paper pipeline."""

from __future__ import annotations

from collections import Counter
import json
from time import perf_counter
from typing import Any

from cegvr.generation.provider import CandidateGenerator

from .types import (
    AttemptRecord,
    CandidateOutput,
    CandidateProposal,
    CandidateVerification,
    ConstraintReference,
    ExperimentArm,
    VerifierFeedback,
)
from .verifier import verify_linear_candidate

_LARGE_RANK = 10**6


def repair_candidates_until_certified(
    problem: dict,
    generator: CandidateGenerator,
    *,
    arm: ExperimentArm,
    max_rounds: int = 4,
    per_round_budget: int = 4,
    timeout_ms: int = 2000,
) -> dict[str, Any]:
    """Iteratively repair candidate outputs under a paper-study arm."""

    total_start = perf_counter()
    history: list[dict[str, Any]] = []
    feedback: VerifierFeedback | None = None
    last_feedback: VerifierFeedback | None = None
    last_feedback_source: dict[str, Any] | None = None
    failure_counts: Counter[tuple[str, ...]] = Counter()
    constraint_variable_map = _constraint_variable_map(problem)
    constraint_text_map = _constraint_text_map(problem)

    llm_attempts = 0
    solver_calls = 0
    llm_latency_ms = 0.0
    solver_latency_ms = 0.0
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    last_predicted_status: str | None = None

    round_limit = 1 if arm is ExperimentArm.ONE_SHOT else max_rounds
    round_budget = 1 if arm is ExperimentArm.ONE_SHOT else per_round_budget

    for round_index in range(1, round_limit + 1):
        proposals = generator.propose_candidates(problem, round_budget, hint=feedback)
        round_attempts: list[tuple[AttemptRecord, CandidateVerification | None]] = []

        for candidate_index, proposal in enumerate(proposals):
            llm_attempts += 1
            llm_latency_ms += proposal.llm_latency_ms
            prompt_tokens += proposal.prompt_tokens or 0
            completion_tokens += proposal.completion_tokens or 0
            total_tokens += proposal.total_tokens or 0

            attempt, verification, predicted_status = _verify_proposal(
                problem=problem,
                proposal=proposal,
                candidate_index=candidate_index,
                round_index=round_index,
                timeout_ms=timeout_ms,
                constraint_variable_map=constraint_variable_map,
                constraint_text_map=constraint_text_map,
                failure_counts=failure_counts,
            )
            history.append(attempt.model_dump(mode="python"))
            round_attempts.append((attempt, verification))
            last_predicted_status = predicted_status

            if verification is not None and verification.verifier_result in {
                "sat",
                "unsat",
                "timeout",
                "unknown",
            }:
                solver_calls += 1
                solver_latency_ms += verification.solver_time_ms

            if attempt.verified_outcome in {"CERTIFIED_SAT", "CERTIFIED_UNSAT"}:
                return _finalize_result(
                    status="certified",
                    verified_outcome=attempt.verified_outcome,
                    predicted_status=attempt.predicted_status,
                    rounds=round_index,
                    total_start=total_start,
                    llm_attempts=llm_attempts,
                    solver_calls=solver_calls,
                    llm_latency_ms=llm_latency_ms,
                    solver_latency_ms=solver_latency_ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    history=history,
                    feedback=last_feedback,
                    feedback_source=last_feedback_source,
                    model=verification.certified_assignment if verification else None,
                    unsat_core=verification.unsat_core if verification else [],
                    arm=arm,
                )

        if arm is ExperimentArm.MULTI_NO_FEEDBACK:
            feedback = None
            continue
        if arm is ExperimentArm.ONE_SHOT:
            break

        source_attempt, source_verification = _select_feedback_source(
            round_attempts, arm
        )
        if source_attempt is None:
            feedback = None
            continue
        feedback = _build_feedback(
            round_index=round_index,
            attempt=source_attempt,
            verification=source_verification,
            arm=arm,
        )
        last_feedback = feedback
        last_feedback_source = {
            "round_index": source_attempt.round_index,
            "candidate_index": source_attempt.candidate_index,
            "verified_outcome": source_attempt.verified_outcome,
            "feedback_source_score": list(source_attempt.feedback_source_score or ()),
            "search_score": list(source_attempt.search_score or ()),
        }

    return _finalize_result(
        status="failed",
        verified_outcome="BUDGET_EXCEEDED",
        predicted_status=last_predicted_status,
        rounds=round_limit,
        total_start=total_start,
        llm_attempts=llm_attempts,
        solver_calls=solver_calls,
        llm_latency_ms=llm_latency_ms,
        solver_latency_ms=solver_latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        history=history,
        feedback=last_feedback,
        feedback_source=last_feedback_source,
        model=None,
        unsat_core=[],
        arm=arm,
    )


def _verify_proposal(
    *,
    problem: dict,
    proposal: CandidateProposal,
    candidate_index: int,
    round_index: int,
    timeout_ms: int,
    constraint_variable_map: dict[str, list[str]],
    constraint_text_map: dict[str, str],
    failure_counts: Counter[tuple[str, ...]],
) -> tuple[AttemptRecord, CandidateVerification | None, str | None]:
    if proposal.candidate is None:
        failure_signature = _failure_signature(
            failure_type="json_or_schema_error",
            verifier_result="parse",
            predicted_status=None,
            constraint_ids=[],
        )
        repeat_failure_count = failure_counts[failure_signature]
        failure_counts[failure_signature] += 1
        search_score = _core_rank_score(
            parse_penalty=1,
            domain_penalty=0,
            precheck_violations=_LARGE_RANK,
            core_size=_LARGE_RANK,
            core_variable_count=_LARGE_RANK,
            repeat_failure_count=repeat_failure_count,
            candidate_index=candidate_index,
        )
        attempt = AttemptRecord(
            round_index=round_index,
            candidate_index=candidate_index,
            predicted_status=None,
            verified_outcome="FAILED_SCHEMA_VALIDATION",
            verifier_result="parse",
            failure_type="json_or_schema_error",
            precheck_violations=_LARGE_RANK,
            unsat_core_size=0,
            llm_latency_ms=proposal.llm_latency_ms,
            solver_latency_ms=0.0,
            prompt_tokens=proposal.prompt_tokens,
            completion_tokens=proposal.completion_tokens,
            total_tokens=proposal.total_tokens,
            raw_candidate=proposal.raw_content,
            failure_signature=failure_signature,
            repeat_failure_count=repeat_failure_count,
            search_score=search_score,
        )
        return attempt, None, None

    verification = verify_linear_candidate(
        problem,
        proposal.candidate,
        timeout_ms=timeout_ms,
    )
    conflict_ids = _conflict_constraint_ids(verification)
    conflict_constraints = _build_conflict_constraints(
        verification=verification,
        conflict_ids=conflict_ids,
        constraint_text_map=constraint_text_map,
    )
    core_variables = _variables_from_constraint_ids(
        constraint_variable_map,
        [ref.constraint_id for ref in verification.unsat_core],
    )
    variables_to_revise = _variables_to_revise(
        problem=problem,
        candidate=proposal.candidate,
        verification=verification,
        constraint_variable_map=constraint_variable_map,
        conflict_ids=conflict_ids,
    )
    previous_assignment = _last_assignment(proposal.candidate, verification)
    variables_to_keep_fixed = _variables_to_keep_fixed(
        problem,
        previous_assignment,
        variables_to_revise,
    )

    failure_signature: tuple[str, ...] | None = None
    repeat_failure_count = 0
    search_score: tuple[int, ...] | None = None
    if verification.verified_outcome not in {"CERTIFIED_SAT", "CERTIFIED_UNSAT"}:
        failure_signature = _failure_signature(
            failure_type=verification.failure_type,
            verifier_result=verification.verifier_result,
            predicted_status=verification.predicted_status,
            constraint_ids=conflict_ids,
        )
        repeat_failure_count = failure_counts[failure_signature]
        failure_counts[failure_signature] += 1
        search_score = _core_rank_score(
            parse_penalty=0,
            domain_penalty=1 if verification.failure_type == "domain_violation" else 0,
            precheck_violations=verification.precheck_violations,
            core_size=len(conflict_ids) if conflict_ids else _LARGE_RANK,
            core_variable_count=len(core_variables) if core_variables else _LARGE_RANK,
            repeat_failure_count=repeat_failure_count,
            candidate_index=candidate_index,
        )

    unsat_core_size = len(verification.unsat_core)
    feedback_source_score = (
        verification.precheck_violations,
        unsat_core_size if unsat_core_size > 0 else _LARGE_RANK,
        candidate_index,
    )
    attempt = AttemptRecord(
        round_index=round_index,
        candidate_index=candidate_index,
        predicted_status=verification.predicted_status,
        verified_outcome=verification.verified_outcome,
        verifier_result=verification.verifier_result,
        failure_type=verification.failure_type,
        precheck_violations=verification.precheck_violations,
        unsat_core_size=unsat_core_size,
        llm_latency_ms=proposal.llm_latency_ms,
        solver_latency_ms=verification.solver_time_ms,
        prompt_tokens=proposal.prompt_tokens,
        completion_tokens=proposal.completion_tokens,
        total_tokens=proposal.total_tokens,
        feedback_source_score=feedback_source_score,
        raw_candidate=proposal.raw_content,
        candidate_output=proposal.candidate.model_dump(mode="python"),
        diagnostics=verification.diagnostics,
        unsat_core=[ref.model_dump(mode="python") for ref in verification.unsat_core],
        sat_witness=verification.sat_witness,
        failure_signature=failure_signature,
        repeat_failure_count=repeat_failure_count,
        search_score=search_score,
        violated_constraint_ids=conflict_ids,
        conflict_constraints=conflict_constraints,
        core_variables=core_variables,
        variables_to_revise=variables_to_revise,
        variables_to_keep_fixed=variables_to_keep_fixed,
    )
    return attempt, verification, verification.predicted_status


def _finalize_result(
    *,
    status: str,
    verified_outcome: str,
    predicted_status: str | None,
    rounds: int,
    total_start: float,
    llm_attempts: int,
    solver_calls: int,
    llm_latency_ms: float,
    solver_latency_ms: float,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    history: list[dict[str, Any]],
    feedback: VerifierFeedback | None,
    feedback_source: dict[str, Any] | None,
    model: dict[str, Any] | None,
    unsat_core: list[ConstraintReference],
    arm: ExperimentArm,
) -> dict[str, Any]:
    payload = {
        "status": status,
        "verified_outcome": verified_outcome,
        "predicted_status": predicted_status,
        "rounds": rounds,
        "latency_ms": (perf_counter() - total_start) * 1000.0,
        "llm_attempts": llm_attempts,
        "solver_calls": solver_calls,
        "llm_latency_ms": llm_latency_ms,
        "solver_latency_ms": solver_latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "history": history,
        "feedback": feedback.model_dump(mode="python")
        if feedback is not None
        else None,
        "feedback_source": feedback_source,
        "selected_parent_round_index": (
            feedback_source.get("round_index") if feedback_source else None
        ),
        "selected_parent_candidate_index": (
            feedback_source.get("candidate_index") if feedback_source else None
        ),
        "search_policy": _search_policy_name(arm),
        "model": model,
        "unsat_core": [ref.model_dump(mode="python") for ref in unsat_core],
    }
    if feedback is not None:
        payload["search_score"] = list(feedback.search_score or ())
        payload["repeat_failure_count"] = feedback.repeat_failure_count
        payload["core_variables"] = feedback.core_variables
        payload["variables_to_revise"] = feedback.variables_to_revise
        payload["variables_to_keep_fixed"] = feedback.variables_to_keep_fixed
    else:
        payload["search_score"] = []
        payload["repeat_failure_count"] = 0
        payload["core_variables"] = []
        payload["variables_to_revise"] = []
        payload["variables_to_keep_fixed"] = []
    return payload


def _search_policy_name(arm: ExperimentArm) -> str:
    if arm is ExperimentArm.CD_VGS_CORE_RANK:
        return "cd_vgs_core_rank"
    if arm is ExperimentArm.ONE_SHOT:
        return "one_shot"
    return "round_retry"


def _select_feedback_source(
    attempts: list[tuple[AttemptRecord, CandidateVerification | None]],
    arm: ExperimentArm,
) -> tuple[AttemptRecord | None, CandidateVerification | None]:
    failed = [
        (attempt, verification)
        for attempt, verification in attempts
        if attempt.verified_outcome not in {"CERTIFIED_SAT", "CERTIFIED_UNSAT"}
    ]
    if not failed:
        return None, None
    if arm is ExperimentArm.CD_VGS_CORE_RANK:
        failed.sort(
            key=lambda pair: (
                pair[0].search_score
                or (
                    _LARGE_RANK,
                    _LARGE_RANK,
                    _LARGE_RANK,
                    _LARGE_RANK,
                    _LARGE_RANK,
                    _LARGE_RANK,
                    pair[0].candidate_index,
                )
            )
        )
    else:
        failed.sort(
            key=lambda pair: (
                pair[0].feedback_source_score
                or (_LARGE_RANK, _LARGE_RANK, pair[0].candidate_index)
            )
        )
    return failed[0]


def _build_feedback(
    *,
    round_index: int,
    attempt: AttemptRecord,
    verification: CandidateVerification | None,
    arm: ExperimentArm,
) -> VerifierFeedback:
    generic_feedback = _generic_feedback_text(attempt)
    if arm is ExperimentArm.MULTI_GENERIC_FEEDBACK or verification is None:
        return VerifierFeedback(
            round_index=round_index,
            failure_type=attempt.failure_type or "unknown_failure",
            verifier_result=attempt.verifier_result,
            generic_feedback=generic_feedback,
            diagnostics={"last_assignment": _attempt_last_assignment(attempt)},
        )
    if arm is ExperimentArm.CD_VGS_CORE_RANK:
        return VerifierFeedback(
            round_index=round_index,
            failure_type=verification.failure_type or "unknown_failure",
            verifier_result=verification.verifier_result,
            generic_feedback=_targeted_repair_instruction(attempt),
            unsat_core=verification.unsat_core,
            sat_witness=verification.sat_witness,
            diagnostics={"last_assignment": _attempt_last_assignment(attempt)},
            variables_to_revise=list(attempt.variables_to_revise),
            variables_to_keep_fixed=list(attempt.variables_to_keep_fixed),
            core_variables=list(attempt.core_variables),
            conflict_constraints=list(attempt.conflict_constraints),
            repeat_failure_count=attempt.repeat_failure_count,
            search_score=attempt.search_score,
        )
    return VerifierFeedback(
        round_index=round_index,
        failure_type=verification.failure_type or "unknown_failure",
        verifier_result=verification.verifier_result,
        generic_feedback=generic_feedback,
        unsat_core=verification.unsat_core,
        sat_witness=verification.sat_witness,
        diagnostics=verification.diagnostics,
    )


def _generic_feedback_text(attempt: AttemptRecord) -> str:
    if attempt.failure_type == "false_unsat_claim":
        return "The previous UNSAT claim was incorrect. If a satisfying assignment exists, return it."
    if attempt.failure_type == "domain_violation":
        return "The previous candidate was incomplete or out of domain. Return a complete in-domain assignment."
    if attempt.verified_outcome == "FAILED_SCHEMA_VALIDATION":
        return "The previous candidate was not valid JSON for the required schema. Return valid JSON only."
    if attempt.verifier_result in {"timeout", "unknown"}:
        return "The verifier could not certify the previous candidate. Return a simpler, cleaner candidate."
    return "The previous candidate failed verification. Revise it and return JSON only."


def _targeted_repair_instruction(attempt: AttemptRecord) -> str:
    if attempt.failure_type == "false_unsat_claim":
        return "The problem is satisfiable. Provide a concrete satisfying assignment and return JSON only."
    if attempt.failure_type == "domain_violation":
        return (
            "Revise the listed variables first so all values stay within the declared "
            "domains and bounds. Keep the fixed set unchanged if possible. Return JSON only."
        )
    return (
        "Revise the listed variables first; keep the fixed set unchanged if possible; "
        "return JSON only."
    )


def _conflict_constraint_ids(verification: CandidateVerification) -> list[str]:
    core_ids = [ref.constraint_id for ref in verification.unsat_core]
    if core_ids:
        return core_ids
    diagnostics = verification.diagnostics or {}
    raw_ids = diagnostics.get("violated_constraint_ids")
    if isinstance(raw_ids, list):
        return [str(item) for item in raw_ids]
    return []


def _build_conflict_constraints(
    *,
    verification: CandidateVerification,
    conflict_ids: list[str],
    constraint_text_map: dict[str, str],
) -> list[ConstraintReference]:
    if verification.unsat_core:
        return list(verification.unsat_core)
    diagnostics = verification.diagnostics or {}
    raw_texts = diagnostics.get("violated_constraint_texts")
    text_lookup: dict[str, str] = {}
    if isinstance(raw_texts, list):
        for constraint_id, text in zip(conflict_ids, raw_texts, strict=False):
            text_lookup[str(constraint_id)] = str(text)
    return [
        ConstraintReference(
            constraint_id=constraint_id,
            constraint_text=text_lookup.get(
                constraint_id, constraint_text_map.get(constraint_id, constraint_id)
            ),
        )
        for constraint_id in conflict_ids
    ]


def _last_assignment(
    candidate: CandidateOutput, verification: CandidateVerification
) -> dict[str, int | bool]:
    diagnostics = verification.diagnostics or {}
    raw_assignment = diagnostics.get("last_assignment")
    if isinstance(raw_assignment, dict):
        return {str(key): value for key, value in raw_assignment.items()}
    if candidate.status == "sat":
        return dict(candidate.assignment or {})
    return {}


def _attempt_last_assignment(attempt: AttemptRecord) -> dict[str, int | bool] | None:
    diagnostics = attempt.model_dump(mode="python").get("diagnostics", {})
    last_assignment = (
        diagnostics.get("last_assignment") if isinstance(diagnostics, dict) else None
    )
    if isinstance(last_assignment, dict):
        return {str(key): value for key, value in last_assignment.items()}
    candidate_output = attempt.model_dump(mode="python").get("candidate_output")
    if isinstance(candidate_output, dict):
        assignment = candidate_output.get("assignment")
        if isinstance(assignment, dict):
            return {str(key): value for key, value in assignment.items()}
    return None


def _variables_to_revise(
    *,
    problem: dict,
    candidate: CandidateOutput,
    verification: CandidateVerification,
    constraint_variable_map: dict[str, list[str]],
    conflict_ids: list[str],
) -> list[str]:
    if verification.failure_type == "domain_violation":
        return _domain_revise_variables(problem, candidate)
    if verification.failure_type == "false_unsat_claim":
        return []
    return _variables_from_constraint_ids(constraint_variable_map, conflict_ids)


def _variables_to_keep_fixed(
    problem: dict,
    last_assignment: dict[str, int | bool],
    variables_to_revise: list[str],
) -> list[str]:
    revise_set = set(variables_to_revise)
    declared_names = [str(spec["name"]) for spec in problem.get("variables", [])]
    return sorted(
        name
        for name in declared_names
        if name in last_assignment and name not in revise_set
    )


def _variables_from_constraint_ids(
    constraint_variable_map: dict[str, list[str]],
    constraint_ids: list[str],
) -> list[str]:
    variables: set[str] = set()
    for constraint_id in constraint_ids:
        variables.update(constraint_variable_map.get(str(constraint_id), []))
    return sorted(variables)


def _domain_revise_variables(problem: dict, candidate: CandidateOutput) -> list[str]:
    assignment = dict(candidate.assignment or {})
    declared: dict[str, dict[str, Any]] = {
        str(spec["name"]): spec for spec in problem.get("variables", [])
    }
    revise: set[str] = set()
    for name, value in assignment.items():
        spec = declared.get(name)
        if spec is None:
            revise.add(name)
            continue
        domain = spec.get("domain", "int")
        bounds = spec.get("bounds") or {}
        if domain == "bool":
            if not isinstance(value, bool):
                revise.add(name)
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            revise.add(name)
            continue
        lower = bounds.get("lower")
        upper = bounds.get("upper")
        if lower is not None and value < int(lower):
            revise.add(name)
        if upper is not None and value > int(upper):
            revise.add(name)
    for name in declared:
        if name not in assignment:
            revise.add(name)
    return sorted(revise)


def _failure_signature(
    *,
    failure_type: str | None,
    verifier_result: str,
    predicted_status: str | None,
    constraint_ids: list[str],
) -> tuple[str, ...]:
    signature = [
        str(failure_type or "unknown_failure"),
        str(verifier_result),
        str(predicted_status or "none"),
    ]
    signature.extend(sorted(str(item) for item in constraint_ids))
    return tuple(signature)


def _core_rank_score(
    *,
    parse_penalty: int,
    domain_penalty: int,
    precheck_violations: int,
    core_size: int,
    core_variable_count: int,
    repeat_failure_count: int,
    candidate_index: int,
) -> tuple[int, ...]:
    return (
        parse_penalty,
        domain_penalty,
        precheck_violations,
        core_size,
        core_variable_count,
        repeat_failure_count,
        candidate_index,
    )


def _constraint_variable_map(problem: dict) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for index, constraint in enumerate(problem.get("constraints", []), start=1):
        constraint_id = str(constraint.get("constraint_id") or f"c{index}")
        mapping[constraint_id] = sorted(_constraint_variables(constraint))
    return mapping


def _constraint_variables(constraint: dict) -> set[str]:
    kind = constraint.get("kind")
    if kind == "linear_ineq":
        return {str(term["variable"]) for term in constraint.get("terms", [])}
    if kind == "int_domain" or kind == "bool_atom":
        variable = constraint.get("variable")
        return {str(variable)} if variable is not None else set()
    if kind == "all_different":
        return {str(name) for name in constraint.get("variables", [])}
    if kind == "and" or kind == "or":
        variables: set[str] = set()
        for child in constraint.get("constraints", []):
            if isinstance(child, dict):
                variables.update(_constraint_variables(child))
        return variables
    if kind == "not":
        child = constraint.get("constraint")
        if isinstance(child, dict):
            return _constraint_variables(child)
    return set()


def _constraint_text_map(problem: dict) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for index, constraint in enumerate(problem.get("constraints", []), start=1):
        constraint_id = str(constraint.get("constraint_id") or f"c{index}")
        mapping[constraint_id] = _describe_constraint(constraint)
    return mapping


def _describe_constraint(constraint: dict) -> str:
    kind = constraint.get("kind")
    if kind == "linear_ineq":
        terms = (
            " + ".join(
                f"({term['coefficient']})*{term['variable']}"
                for term in constraint.get("terms", [])
            )
            or "0"
        )
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


__all__ = [
    "repair_candidates_until_certified",
    "_constraint_variables",
    "_failure_signature",
    "_variables_from_constraint_ids",
]
