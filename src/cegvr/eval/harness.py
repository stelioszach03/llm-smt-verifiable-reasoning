"""Evaluation harness for running the repair loop over datasets."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from time import perf_counter
from typing import Iterable

from tqdm.auto import tqdm

from cegvr.data.loader import iter_jsonl_problems
from cegvr.engine.configs import DEFAULT_EXPERIMENT_CONFIG, ExperimentConfig
from cegvr.engine.repair import repair_until_certified
from cegvr.generation.provider import TraceGenerator


def run_evaluation(
    *,
    dataset_path: Path | str,
    output_path: Path | str,
    generator: TraceGenerator,
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
                outcome = repair_until_certified(
                    {**problem, "seed": seed},
                    generator,
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
                    "status": outcome.get("status"),
                    "certified": outcome.get("status") == "certified",
                    "uncertified_correct": outcome.get("status") != "certified"
                    and problem.get("ground_truth") == "unsat",
                    "iterations": outcome.get("rounds"),
                    "latency_ms": int(latency_ms),
                    "solver_calls": int(solver_calls),
                    "config": outcome.get("config", cfg.to_dict()),
                    "budget": per_round_budget,
                    "max_rounds": max_rounds,
                    "timeout_ms": timeout_ms,
                }
                if "trace" in outcome:
                    record["trace"] = outcome["trace"]
                if "model" in outcome:
                    record["model"] = outcome["model"]
                if "history" in outcome:
                    record["history"] = outcome["history"]
                if outcome.get("status") == "failed" and outcome.get("feedback"):
                    record["feedback"] = outcome["feedback"]
                sink.write(json.dumps(record, sort_keys=True))
                sink.write("\n")
        logger.info("Completed seed %s", seed)


__all__ = ["run_evaluation"]
