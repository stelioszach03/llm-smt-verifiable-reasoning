"""Aggregation utilities for evaluation outputs."""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from cegvr.data.loader import VALID_TASKS


@dataclass
class MetricSummary:
    value: float
    lower: float
    upper: float


def _bootstrap_ci(
    samples: Sequence[float], *, num_samples: int = 1000, alpha: float = 0.05
) -> MetricSummary:
    if not samples:
        return MetricSummary(0.0, 0.0, 0.0)

    rng = random.Random(42)
    estimates: List[float] = []
    for _ in range(num_samples):
        resample = [samples[rng.randrange(len(samples))] for _ in samples]
        estimates.append(sum(resample) / len(resample))
    estimates.sort()

    lower_index = int((alpha / 2) * len(estimates))
    upper_index = int((1 - alpha / 2) * len(estimates))
    return MetricSummary(
        value=sum(samples) / len(samples),
        lower=estimates[max(0, lower_index)],
        upper=estimates[min(len(estimates) - 1, upper_index)],
    )


def _point_summary(value: float) -> Dict[str, float]:
    return MetricSummary(value=value, lower=value, upper=value).__dict__


def _percentile(samples: Sequence[float], percentile: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    if len(ordered) == 1:
        return float(ordered[0])
    index = (len(ordered) - 1) * percentile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return float(ordered[int(index)])
    lower_value = float(ordered[lower])
    upper_value = float(ordered[upper])
    return lower_value + (upper_value - lower_value) * (index - lower)


def load_run(path: Path | str) -> List[Dict[str, Any]]:
    target = Path(path)
    records: List[Dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            records.append(json.loads(line))
    return records


def aggregate_runs(paths: Iterable[Path | str]) -> Dict[str, Any]:
    combined: List[Dict[str, Any]] = []
    for run_path in paths:
        combined.extend(load_run(run_path))

    per_task: Dict[str, int] = {task: 0 for task in VALID_TASKS}
    for record in combined:
        task = str(record.get("task"))
        if task in per_task:
            per_task[task] += 1

    overall = _summarize_records(combined)
    grouped_by_arm = _group_records_by_arm(combined)
    by_arm = {arm: _summarize_records(items) for arm, items in grouped_by_arm.items()}
    by_arm_per_difficulty = {
        arm: _summarize_by_difficulty(items) for arm, items in grouped_by_arm.items()
    }
    comparisons = _paired_arm_comparisons(grouped_by_arm)
    if "one_shot" in by_arm:
        baseline = by_arm["one_shot"]["verified_solve_rate"]["value"]
        for payload in by_arm.values():
            payload["repair_gain_vs_one_shot"] = _point_summary(
                payload["verified_solve_rate"]["value"] - baseline
            )

    summary: Dict[str, Any] = {
        "count": len(combined),
        "per_task": per_task,
        "overall": overall,
        "per_arm": by_arm,
        "per_arm_per_difficulty": by_arm_per_difficulty,
        "comparisons": comparisons,
        # Backward-tolerant aliases for existing lightweight consumers.
        "certified_accuracy": overall["verified_solve_rate"],
        "avg_iterations": overall["avg_iterations"],
        "avg_latency_ms": overall["latency_mean_ms"],
    }

    return summary


def _group_records_by_arm(
    records: Sequence[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        arm = str(record.get("arm") or "unknown")
        grouped.setdefault(arm, []).append(record)
    return grouped


def _difficulty_bin(record: Dict[str, Any]) -> str:
    features = record.get("problem_features")
    if isinstance(features, dict):
        value = features.get("difficulty_bin")
        if value:
            return str(value)
    return "unknown"


def _summarize_by_difficulty(
    records: Sequence[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(_difficulty_bin(record), []).append(record)
    return {
        difficulty: _summarize_records(items) for difficulty, items in grouped.items()
    }


def _summarize_records(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(records)
    verified_solve = [1.0 if _is_certified(record) else 0.0 for record in records]
    sat_records = [record for record in records if record.get("ground_truth") == "sat"]
    unsat_records = [
        record for record in records if record.get("ground_truth") == "unsat"
    ]
    sat_certified = [
        1.0 if record.get("verified_outcome") == "CERTIFIED_SAT" else 0.0
        for record in sat_records
    ]
    predicted_unsat = [
        record for record in records if str(record.get("predicted_status")) == "unsat"
    ]
    unsat_precision = [
        1.0 if record.get("ground_truth") == "unsat" else 0.0
        for record in predicted_unsat
    ]
    unsat_recall = [
        1.0 if str(record.get("predicted_status")) == "unsat" else 0.0
        for record in unsat_records
    ]
    iterations = [float(record.get("iterations", 0) or 0.0) for record in records]
    latency = [float(record.get("latency_ms", 0.0) or 0.0) for record in records]
    llm_latency = [
        float(record.get("llm_latency_ms", 0.0) or 0.0) for record in records
    ]
    solver_latency = [
        float(record.get("solver_latency_ms", 0.0) or 0.0) for record in records
    ]
    solver_calls = [float(record.get("solver_calls", 0.0) or 0.0) for record in records]
    tokens = [float(record.get("total_tokens", 0.0) or 0.0) for record in records]
    certified_count = sum(1 for record in records if _is_certified(record))

    return {
        "count": total,
        "verified_solve_rate": _bootstrap_ci(verified_solve).__dict__,
        "sat_certification_rate": _bootstrap_ci(sat_certified).__dict__
        if sat_certified
        else _point_summary(0.0),
        "unsat_precision": _bootstrap_ci(unsat_precision).__dict__
        if unsat_precision
        else _point_summary(0.0),
        "unsat_recall": _bootstrap_ci(unsat_recall).__dict__
        if unsat_recall
        else _point_summary(0.0),
        "solver_calls_per_certified_solve": _point_summary(
            (sum(solver_calls) / certified_count) if certified_count else 0.0
        ),
        "tokens_per_certified_solve": _point_summary(
            (sum(tokens) / certified_count) if certified_count else 0.0
        ),
        "avg_iterations": _bootstrap_ci(iterations).__dict__
        if iterations
        else _point_summary(0.0),
        "latency_mean_ms": _bootstrap_ci(latency).__dict__
        if latency
        else _point_summary(0.0),
        "latency_median_ms": _point_summary(_percentile(latency, 0.5)),
        "latency_p95_ms": _point_summary(_percentile(latency, 0.95)),
        "llm_latency_mean_ms": _bootstrap_ci(llm_latency).__dict__
        if llm_latency
        else _point_summary(0.0),
        "solver_latency_mean_ms": _bootstrap_ci(solver_latency).__dict__
        if solver_latency
        else _point_summary(0.0),
    }


def _is_certified(record: Dict[str, Any]) -> bool:
    return str(record.get("verified_outcome")) in {
        "CERTIFIED_SAT",
        "CERTIFIED_UNSAT",
    }


def _paired_arm_comparisons(
    grouped_by_arm: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    if len(grouped_by_arm) < 2:
        return {}
    comparisons: Dict[str, Any] = {}
    multi_arms = [
        arm
        for arm in sorted(grouped_by_arm)
        if arm
        in {
            "multi_no_feedback",
            "multi_generic_feedback",
            "multi_unsat_core_feedback",
            "cd_vgs_core_rank",
        }
    ]
    raw_p_values: list[tuple[str, float]] = []
    for arm_a_index, arm_a in enumerate(multi_arms):
        for arm_b in multi_arms[arm_a_index + 1 :]:
            pair_key = f"{arm_a}__vs__{arm_b}"
            pair_summary = _paired_comparison_summary(
                grouped_by_arm[arm_a], grouped_by_arm[arm_b]
            )
            comparisons[pair_key] = pair_summary
            raw_p_values.append((pair_key, pair_summary["success_mcnemar_p"]))
    adjusted = _holm_adjust(raw_p_values)
    for pair_key, adjusted_value in adjusted.items():
        if pair_key in comparisons:
            comparisons[pair_key]["success_mcnemar_p_holm"] = adjusted_value
    return comparisons


def _holm_adjust(items: list[tuple[str, float]]) -> Dict[str, float]:
    adjusted: Dict[str, float] = {}
    running_max = 0.0
    total = len(items)
    for index, (name, p_value) in enumerate(sorted(items, key=lambda item: item[1])):
        corrected = min(1.0, p_value * (total - index))
        running_max = max(running_max, corrected)
        adjusted[name] = running_max
    return adjusted


def _paired_comparison_summary(
    arm_a_records: Sequence[Dict[str, Any]],
    arm_b_records: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    indexed_a = {_pair_key(record): record for record in arm_a_records}
    indexed_b = {_pair_key(record): record for record in arm_b_records}
    shared_keys = sorted(set(indexed_a) & set(indexed_b))
    paired = [(indexed_a[key], indexed_b[key]) for key in shared_keys]
    success_pairs = [
        (1 if _is_certified(left) else 0, 1 if _is_certified(right) else 0)
        for left, right in paired
    ]
    latency_pairs = [
        (
            float(left.get("latency_ms", 0.0) or 0.0),
            float(right.get("latency_ms", 0.0) or 0.0),
        )
        for left, right in paired
    ]
    solver_call_pairs = [
        (
            float(left.get("solver_calls", 0.0) or 0.0),
            float(right.get("solver_calls", 0.0) or 0.0),
        )
        for left, right in paired
    ]
    return {
        "n_pairs": len(paired),
        "success_mcnemar_p": _mcnemar_exact(success_pairs),
        "latency_wilcoxon_p": _wilcoxon_signed_rank(latency_pairs),
        "solver_calls_wilcoxon_p": _wilcoxon_signed_rank(solver_call_pairs),
    }


def _pair_key(record: Dict[str, Any]) -> tuple[Any, Any]:
    return (record.get("seed"), record.get("problem_id"))


def _mcnemar_exact(pairs: Sequence[tuple[int, int]]) -> float:
    b = sum(1 for left, right in pairs if left == 1 and right == 0)
    c = sum(1 for left, right in pairs if left == 0 and right == 1)
    total = b + c
    if total == 0:
        return 1.0
    cutoff = min(b, c)
    tail = sum(math.comb(total, i) for i in range(cutoff + 1)) / (2**total)
    return min(1.0, 2.0 * tail)


def _wilcoxon_signed_rank(pairs: Sequence[tuple[float, float]]) -> float:
    diffs = [left - right for left, right in pairs if left != right]
    if not diffs:
        return 1.0
    ranks = _rank_abs(diffs)
    positive = sum(rank for diff, rank in zip(diffs, ranks, strict=False) if diff > 0)
    negative = sum(rank for diff, rank in zip(diffs, ranks, strict=False) if diff < 0)
    statistic = min(positive, negative)
    n = len(diffs)
    mean = n * (n + 1) / 4.0
    variance = n * (n + 1) * (2 * n + 1) / 24.0
    if variance <= 0.0:
        return 1.0
    z = (abs(statistic - mean) - 0.5) / math.sqrt(variance)
    return math.erfc(z / math.sqrt(2.0))


def _rank_abs(diffs: Sequence[float]) -> list[float]:
    indexed = sorted(
        enumerate(abs(diff) for diff in diffs),
        key=lambda item: item[1],
    )
    ranks = [0.0] * len(diffs)
    cursor = 0
    while cursor < len(indexed):
        end = cursor + 1
        while end < len(indexed) and indexed[end][1] == indexed[cursor][1]:
            end += 1
        average_rank = (cursor + 1 + end) / 2.0
        for position in range(cursor, end):
            original_index = indexed[position][0]
            ranks[original_index] = average_rank
        cursor = end
    return ranks


__all__ = ["aggregate_runs", "load_run", "MetricSummary"]
