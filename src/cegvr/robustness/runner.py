"""Core robustness evaluation utilities."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
from tqdm.auto import tqdm

from cegvr.data.loader import iter_jsonl_problems
from cegvr.engine.configs import ExperimentConfig
from cegvr.engine.repair import repair_until_certified
from cegvr.generation.provider import TraceGenerator

from .paraphrase import paraphrase_problem
from .spec_variations import generate_variants

LOGGER = logging.getLogger(__name__)


def load_problems(path: Path | str) -> List[dict]:
    return list(iter_jsonl_problems(path))


def evaluate_problem(
    problem: dict, generator: TraceGenerator, config: ExperimentConfig
) -> dict:
    return repair_until_certified(problem, generator, config=config)


def evaluate_variants(
    problems: List[dict],
    *,
    variants: int,
    generator: TraceGenerator,
    config: ExperimentConfig,
) -> List[dict]:
    results: List[dict] = []
    for problem in tqdm(problems, desc="robustness", leave=False):
        base_outcome = evaluate_problem(problem, generator, config)
        results.append({"variant": "base", "problem": problem, "outcome": base_outcome})

        para_problem = paraphrase_problem(problem)
        paraphrase_outcome = evaluate_problem(para_problem, generator, config)
        results.append(
            {
                "variant": "paraphrase",
                "problem": para_problem,
                "outcome": paraphrase_outcome,
            }
        )

        for idx, variant in enumerate(generate_variants(problem, variants)):
            outcome = evaluate_problem(variant, generator, config)
            results.append(
                {"variant": f"spec_{idx}", "problem": variant, "outcome": outcome}
            )
    LOGGER.info("Robustness evaluation completed for %s problems", len(problems))
    return results


def write_results(results: List[dict], output_dir: Path | str) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "robustness.jsonl"
    with target.open("w", encoding="utf-8") as handle:
        for record in results:
            handle.write(json.dumps(record, sort_keys=True))
            handle.write("\n")
    return target


def aggregate_deltas(results: List[dict]) -> Dict[str, float]:
    base_certified: Dict[str, float] = {}
    for record in results:
        if record["variant"] == "base":
            pid = str(record["problem"].get("problem_id"))
            base_certified[pid] = (
                1.0 if record["outcome"].get("status") == "certified" else 0.0
            )

    deltas: Dict[str, List[float]] = {}
    for record in results:
        variant = record["variant"]
        pid = str(record["problem"].get("problem_id"))
        certified = 1.0 if record["outcome"].get("status") == "certified" else 0.0
        baseline = base_certified.get(pid, 0.0)
        deltas.setdefault(variant, []).append(certified - baseline)

    return {
        key: (sum(values) / len(values) if values else 0.0)
        for key, values in deltas.items()
    }


def save_delta_table(deltas: Dict[str, float], output_csv: Path | str) -> None:
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8") as handle:
        handle.write("variant,delta_certified\n")
        for variant, value in sorted(deltas.items()):
            handle.write(f"{variant},{value:.4f}\n")


def save_delta_plot(deltas: Dict[str, float], output_path: Path | str) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    variants = sorted(deltas)
    values = [deltas[v] for v in variants]
    fig, ax = plt.subplots(figsize=(5, 3))
    ax.bar(variants, values)
    ax.set_ylabel("Δ Certified Accuracy")
    ax.set_xlabel("Variant Type")
    ax.axhline(0, color="black", linewidth=1)
    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


__all__ = [
    "load_problems",
    "evaluate_problem",
    "evaluate_variants",
    "write_results",
    "aggregate_deltas",
    "save_delta_table",
    "save_delta_plot",
]
