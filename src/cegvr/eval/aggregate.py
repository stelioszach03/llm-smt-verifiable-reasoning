"""Aggregation utilities for evaluation outputs."""

from __future__ import annotations

import json
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

    certified_values = [1.0 if record.get("certified") else 0.0 for record in combined]
    uncertified_correct_values = [
        1.0 if record.get("uncertified_correct") else 0.0 for record in combined
    ]
    iterations = [record.get("iterations", 0) for record in combined]
    latency = [record.get("latency_ms", 0.0) for record in combined]

    per_task: Dict[str, int] = {task: 0 for task in VALID_TASKS}
    for record in combined:
        task = str(record.get("task"))
        if task in per_task:
            per_task[task] += 1

    summary: Dict[str, Any] = {
        "count": len(combined),
        "certified_accuracy": _bootstrap_ci(certified_values).__dict__,
        "uncertified_accuracy": _bootstrap_ci(uncertified_correct_values).__dict__,
        "avg_iterations": _bootstrap_ci(iterations).__dict__,
        "avg_latency_ms": _bootstrap_ci(latency).__dict__,
        "per_task": per_task,
    }

    return summary


__all__ = ["aggregate_runs", "load_run", "MetricSummary"]
