"""Repair loop for generating certified reasoning traces."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from importlib import resources
from time import perf_counter
from typing import Any, Dict, List

import jsonschema
from pydantic import ValidationError as PydanticValidationError

from cegvr.baselines.dummy import build_dummy_trace
from cegvr.generation.provider import TraceGenerator
from cegvr.grammar.types import Trace
from cegvr.smt.runner import check_trace

from .configs import DEFAULT_EXPERIMENT_CONFIG, ExperimentConfig
from .errors import (
    GenerationError,
    NoCoverage,
    SolverTimeout,
    SolverUnknown,
    ValidationError,
)

LOGGER = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_trace_schema() -> Dict[str, Any]:
    data = (
        resources.files("cegvr.grammar")
        .joinpath("schema.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(data)


def _coerce_trace(candidate: Dict[str, Any]) -> Trace:
    """Attempt to coerce a loosely structured payload into a Trace."""

    payload = dict(candidate)
    payload.setdefault("problem_id", "coerced-problem")
    payload.setdefault("task", "math")
    payload.setdefault("variables", [])
    payload.setdefault("assumptions", [])
    payload.setdefault("steps", [])
    payload.setdefault("constraints", [])
    payload.setdefault("objective", {"type": "value"})
    payload.setdefault(
        "answer", {"value": {}, "justification": "Coerced without grammar"}
    )
    return Trace.model_validate(payload)


def repair_until_certified(
    problem: dict,
    generator: TraceGenerator,
    *,
    max_rounds: int = 5,
    per_round_budget: int = 2,
    timeout_ms: int = 2000,
    config: ExperimentConfig | None = None,
) -> Dict[str, Any]:
    """Iteratively refine candidate traces until certification or failure."""

    cfg = config or DEFAULT_EXPERIMENT_CONFIG
    config_dict = cfg.to_dict()
    total_start = perf_counter()

    if not cfg.use_solver:
        baseline_trace = build_dummy_trace(problem)
        value = baseline_trace.get("answer", {}).get("value", {})
        latency = (perf_counter() - total_start) * 1000
        LOGGER.info(
            "Returning baseline solution without solver for problem %s",
            problem.get("problem_id"),
        )
        return {
            "status": "baseline",
            "rounds": 1,
            "latency_ms": latency,
            "trace": baseline_trace,
            "model": value,
            "history": [{"round": 1, "status": "baseline"}],
            "config": config_dict,
            "solver_calls": 0,
        }

    schema = _load_trace_schema() if cfg.use_grammar else None
    feedback: dict | None = None
    history: List[Dict[str, Any]] = []
    rounds_used = 0
    solver_calls = 0
    round_limit = max_rounds if cfg.enable_repair else 1

    for round_index in range(round_limit):
        rounds_used = round_index + 1
        round_feedback: List[Dict[str, Any]] = []
        candidates = generator.propose(problem, per_round_budget, hint=feedback)
        LOGGER.info("Round %s generated %s candidates", rounds_used, len(candidates))

        if not candidates:
            err = GenerationError(
                "Generator returned no candidates", context={"round": rounds_used}
            )
            history.append(
                {
                    "round": rounds_used,
                    "status": "no_candidates",
                    "error": err.as_dict(),
                }
            )
            feedback = {"round": rounds_used, "issues": [err.as_dict()]}
            LOGGER.warning("No candidates generated on round %s", rounds_used)
            continue

        for candidate_index, candidate in enumerate(candidates):
            entry: Dict[str, Any] = {
                "round": rounds_used,
                "candidate_index": candidate_index,
            }

            try:
                if schema is not None:
                    jsonschema.validate(instance=candidate, schema=schema)
                    trace = Trace.model_validate(candidate)
                else:
                    trace = _coerce_trace(candidate)
            except (jsonschema.ValidationError, PydanticValidationError) as exc:
                val_err = ValidationError(
                    "Trace failed validation",
                    context={"candidate_index": candidate_index, "detail": str(exc)},
                )
                entry.update({"status": "invalid", "error": val_err.as_dict()})
                history.append(entry)
                round_feedback.append(val_err.as_dict())
                LOGGER.error(
                    "Validation error for problem %s candidate %s: %s",
                    problem.get("problem_id"),
                    candidate_index,
                    exc,
                )
                continue

            solver_result = check_trace(trace, timeout_ms=timeout_ms)
            solver_calls += 1
            entry.update({"status": solver_result["status"], "solver": solver_result})
            history.append(entry)
            LOGGER.info(
                "Solver result for problem %s candidate %s: %s",
                problem.get("problem_id"),
                candidate_index,
                solver_result["status"],
            )

            if solver_result["status"] == "sat":
                total_latency = (perf_counter() - total_start) * 1000
                LOGGER.info(
                    "Certified solution found for problem %s", problem.get("problem_id")
                )
                return {
                    "status": "certified",
                    "rounds": rounds_used,
                    "latency_ms": total_latency,
                    "trace": trace.model_dump(mode="python"),
                    "model": solver_result.get("model", {}),
                    "history": history,
                    "config": config_dict,
                    "solver_calls": solver_calls,
                }

            if solver_result["status"] == "unsat":
                # attach last assignment for guided revision
                last_assignment = (
                    getattr(getattr(trace, "answer", None), "value", {}) or {}
                )
                issue = {
                    "type": "unsat_core",
                    "unsat_core": solver_result.get("unsat_core", []),
                    "last_assignment": last_assignment,
                }
                if solver_result.get("unsat_descriptions"):
                    issue["unsat_descriptions"] = solver_result["unsat_descriptions"]
                round_feedback.append(issue)
            elif solver_result["status"] == "timeout":
                timeout_err = SolverTimeout(
                    "Solver timed out", context={"timeout_ms": timeout_ms}
                )
                issue = timeout_err.as_dict()
                round_feedback.append(issue)
                LOGGER.warning(
                    "Solver timeout for problem %s", problem.get("problem_id")
                )
            else:  # unknown or others
                unknown_err = SolverUnknown(
                    "Solver returned unknown",
                    context={"reason": solver_result.get("reason")},
                )
                issue = unknown_err.as_dict()
                round_feedback.append(issue)
                LOGGER.warning(
                    "Solver returned unknown for problem %s: %s",
                    problem.get("problem_id"),
                    solver_result.get("reason"),
                )

        feedback = (
            {"round": rounds_used, "issues": round_feedback} if round_feedback else None
        )

    total_latency = (perf_counter() - total_start) * 1000
    if rounds_used == 0:
        no_coverage_err = NoCoverage(
            "Repair loop performed zero iterations",
            context={"problem_id": problem.get("problem_id")},
        )
        history.append({"status": "no_coverage", "error": no_coverage_err.as_dict()})
    LOGGER.warning(
        "Repair loop ended without certification for problem %s after %s rounds",
        problem.get("problem_id"),
        rounds_used,
    )
    return {
        "status": "failed",
        "rounds": rounds_used,
        "latency_ms": total_latency,
        "history": history,
        "feedback": feedback,
        "config": config_dict,
        "solver_calls": solver_calls,
    }


__all__ = ["repair_until_certified"]
