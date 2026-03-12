"""Evaluation harness for running the repair loop over datasets."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable

from cegvr.candidate.repair import repair_candidates_until_certified
from cegvr.candidate.types import ExperimentArm
from tqdm.auto import tqdm

from cegvr.data.loader import iter_jsonl_problems
from cegvr.engine.configs import DEFAULT_EXPERIMENT_CONFIG, ExperimentConfig
from cegvr.engine.repair import repair_until_certified
from cegvr.generation.provider import CandidateGenerator, TraceGenerator


def run_evaluation(
    *,
    dataset_path: Path | str,
    output_path: Path | str,
    generator: TraceGenerator | CandidateGenerator,
    seeds: Iterable[int],
    max_rounds: int,
    per_round_budget: int,
    timeout_ms: int,
    config: ExperimentConfig | None = None,
) -> None:
    """Execute the repair loop across the dataset for multiple seeds."""

    logger = logging.getLogger(__name__)
    dataset = list(iter_jsonl_problems(dataset_path))
    output_root = Path(output_path)
    output_root.mkdir(parents=True, exist_ok=True)
    cfg = config or DEFAULT_EXPERIMENT_CONFIG
    seed_list = list(seeds)
    logger.info(
        "Starting evaluation: %s problems x %s seeds", len(dataset), len(seed_list)
    )

    for seed in seed_list:
        seed_path = output_root / f"seed_{seed}.jsonl"
        with seed_path.open("w", encoding="utf-8") as sink:
            for problem in tqdm(dataset, desc=f"seed {seed}", leave=False):
                start = perf_counter()
                problem_with_seed = {**problem, "seed": seed}
                if cfg.pipeline == "candidate":
                    outcome = repair_candidates_until_certified(
                        problem_with_seed,
                        generator,  # type: ignore[arg-type]
                        arm=cfg.arm,
                        max_rounds=max_rounds,
                        per_round_budget=per_round_budget,
                        timeout_ms=timeout_ms,
                    )
                else:
                    outcome = repair_until_certified(
                        problem_with_seed,
                        generator,  # type: ignore[arg-type]
                        max_rounds=max_rounds,
                        per_round_budget=per_round_budget,
                        timeout_ms=timeout_ms,
                        config=cfg,
                    )
                latency_ms = (
                    outcome.get("latency_ms") or (perf_counter() - start) * 1000
                )
                solver_calls = outcome.get("solver_calls")
                if solver_calls is None:
                    solver_calls = sum(
                        1
                        for entry in outcome.get("history", [])
                        if entry.get("status") in {"sat", "unsat", "timeout", "unknown"}
                    )
                record = {
                    "seed": seed,
                    "problem_id": problem.get("problem_id"),
                    "task": problem.get("task"),
                    "ground_truth": problem.get("ground_truth"),
                    "pipeline": cfg.pipeline,
                    "arm": cfg.arm.value,
                    "status": outcome.get("status"),
                    "certified": outcome.get("status") == "certified",
                    "predicted_status": outcome.get("predicted_status"),
                    "verified_outcome": outcome.get("verified_outcome"),
                    "iterations": outcome.get("rounds"),
                    "latency_ms": float(latency_ms),
                    "solver_calls": int(solver_calls),
                    "llm_attempts": int(outcome.get("llm_attempts", 0) or 0),
                    "llm_latency_ms": float(outcome.get("llm_latency_ms", 0.0) or 0.0),
                    "solver_latency_ms": float(
                        outcome.get("solver_latency_ms", 0.0) or 0.0
                    ),
                    "prompt_tokens": int(outcome.get("prompt_tokens", 0) or 0),
                    "completion_tokens": int(outcome.get("completion_tokens", 0) or 0),
                    "total_tokens": int(outcome.get("total_tokens", 0) or 0),
                    "config": outcome.get("config", cfg.to_dict()),
                    "per_round_candidates": per_round_budget,
                    "max_rounds": max_rounds,
                    "timeout_ms": timeout_ms,
                    "effective_attempt_budget": (
                        1
                        if cfg.arm is ExperimentArm.ONE_SHOT
                        else per_round_budget * max_rounds
                    ),
                    "search_policy": outcome.get("search_policy")
                    or (
                        "cd_vgs_core_rank"
                        if cfg.arm is ExperimentArm.CD_VGS_CORE_RANK
                        else (
                            "one_shot"
                            if cfg.arm is ExperimentArm.ONE_SHOT
                            else "round_retry"
                        )
                    ),
                    "search_score": outcome.get("search_score", []),
                    "repeat_failure_count": int(
                        outcome.get("repeat_failure_count", 0) or 0
                    ),
                    "core_variables": outcome.get("core_variables", []),
                    "variables_to_revise": outcome.get("variables_to_revise", []),
                    "variables_to_keep_fixed": outcome.get(
                        "variables_to_keep_fixed", []
                    ),
                    "selected_parent_round_index": outcome.get(
                        "selected_parent_round_index"
                    ),
                    "selected_parent_candidate_index": outcome.get(
                        "selected_parent_candidate_index"
                    ),
                    "problem_features": _problem_features(problem),
                }
                if "trace" in outcome:
                    record["trace"] = outcome["trace"]
                if "model" in outcome:
                    record["model"] = outcome["model"]
                if "history" in outcome:
                    record["history"] = outcome["history"]
                if outcome.get("feedback"):
                    record["feedback"] = outcome["feedback"]
                if outcome.get("feedback_source"):
                    record["feedback_source"] = outcome["feedback_source"]
                failure_type = _failure_type(outcome, record)
                if failure_type is not None:
                    record["failure_type"] = failure_type
                sink.write(json.dumps(record, sort_keys=True))
                sink.write("\n")
        logger.info("Completed seed %s", seed)


def _failure_type(outcome: dict, record: dict) -> str | None:
    if outcome.get("failure_type"):
        return str(outcome["failure_type"])
    history = record.get("history", [])
    if isinstance(history, list) and history:
        last = history[-1]
        if isinstance(last, dict) and last.get("failure_type"):
            return str(last["failure_type"])
    return None


def _problem_features(problem: dict) -> dict:
    constraints = problem.get("constraints", [])
    variables = problem.get("variables", [])
    n_vars = len(variables)
    n_constraints = len(constraints)
    coeffs: list[float] = []
    for constraint in constraints:
        if constraint.get("kind") == "linear_ineq":
            for term in constraint.get("terms", []):
                try:
                    coeffs.append(abs(float(term.get("coefficient", 0.0))))
                except (TypeError, ValueError):
                    continue
    raw_meta = problem.get("metadata")
    metadata: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    return {
        "n_vars": n_vars,
        "n_constraints": n_constraints,
        "constraint_to_var_ratio": (
            float(n_constraints) / float(n_vars) if n_vars else 0.0
        ),
        "coeff_max_abs": max(coeffs) if coeffs else 0.0,
        "difficulty_bin": metadata.get("difficulty_bin"),
        "offline_solver_time_ms": metadata.get("offline_solver_time_ms"),
        "offline_unsat_core_size": metadata.get("unsat_core_size"),
    }


__all__ = ["run_evaluation"]
