"""Plotting utilities for evaluation outputs."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Iterable, List, Sequence

import matplotlib.pyplot as plt

from cegvr.eval.aggregate import load_run


def load_records_from_runs(run_paths: Iterable[Path]) -> List[dict]:
    """Load and merge JSONL run records."""

    records: List[dict] = []
    for path in run_paths:
        records.extend(load_run(path))
    return records


def plot_certification_vs_budget(records: Sequence[dict], output_path: Path) -> None:
    """Plot certification accuracy as a function of repair budget."""

    by_budget: dict[int, List[float]] = defaultdict(list)
    for record in records:
        budget = record.get("budget")
        certified = record.get("certified")
        if budget is None or certified is None:
            continue
        by_budget[int(budget)].append(1.0 if certified else 0.0)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(5, 3))

    if by_budget:
        budgets = sorted(by_budget)
        accuracies = [mean(by_budget[b]) for b in budgets]
        ax.plot(budgets, accuracies, marker="o")
        ax.set_xlabel("Per-round budget")
        ax.set_ylabel("Certified accuracy")
        ax.set_ylim(0, 1)
    else:
        ax.text(0.5, 0.5, "No budget annotations available", ha="center", va="center")
        ax.set_axis_off()

    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def plot_iterations_histogram(records: Sequence[dict], output_path: Path) -> None:
    """Plot a histogram of repair iterations."""

    iterations = [int(record.get("iterations", 0) or 0) for record in records]
    iterations = [value for value in iterations if value > 0]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(5, 3))

    if iterations:
        max_iter = max(iterations)
        bins = range(1, max_iter + 2)
        ax.hist(iterations, bins=bins, edgecolor="black")
        ax.set_xlabel("Iterations")
        ax.set_ylabel("Frequency")
    else:
        ax.text(0.5, 0.5, "No iteration data available", ha="center", va="center")
        ax.set_axis_off()

    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def plot_latency_accuracy_pareto(records: Sequence[dict], output_path: Path) -> None:
    """Plot a latency vs certified-accuracy Pareto scatter."""

    per_problem: dict[str, List[dict]] = defaultdict(list)
    for record in records:
        problem_id = record.get("problem_id")
        if not problem_id:
            continue
        per_problem[str(problem_id)].append(record)

    points = []
    for entries in per_problem.values():
        latencies = [float(entry.get("latency_ms", 0.0) or 0.0) for entry in entries]
        certified_flags = [1.0 if entry.get("certified") else 0.0 for entry in entries]
        if not latencies:
            continue
        latency = mean(latencies)
        accuracy = mean(certified_flags) if certified_flags else 0.0
        points.append((latency, accuracy))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(5, 3))

    if points:
        xs, ys = zip(*points, strict=False)
        ax.scatter(xs, ys, alpha=0.7)
        ax.set_xlabel("Latency (ms)")
        ax.set_ylabel("Certified accuracy")
        ax.set_ylim(0, 1)
    else:
        ax.text(0.5, 0.5, "No latency data available", ha="center", va="center")
        ax.set_axis_off()

    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


__all__ = [
    "load_records_from_runs",
    "plot_certification_vs_budget",
    "plot_iterations_histogram",
    "plot_latency_accuracy_pareto",
]
