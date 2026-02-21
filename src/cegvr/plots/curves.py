"""Plotting utilities for evaluation outputs."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Iterable, List, Sequence

import matplotlib.pyplot as plt

from cegvr.eval.aggregate import load_run

_ARM_ORDER = {
    "one_shot": 0,
    "multi_no_feedback": 1,
    "multi_generic_feedback": 2,
    "multi_unsat_core_feedback": 3,
    "cd_vgs_core_rank": 4,
}


def load_records_from_runs(run_paths: Iterable[Path]) -> List[dict]:
    """Load and merge JSONL run records."""

    records: List[dict] = []
    for path in run_paths:
        records.extend(load_run(path))
    return records


def plot_arm_verified_solve_rate(records: Sequence[dict], output_path: Path) -> None:
    """Plot verified solve rate per arm."""

    by_arm: dict[str, List[float]] = defaultdict(list)
    for record in records:
        arm = str(record.get("arm") or "unknown")
        verified = str(record.get("verified_outcome")) in {
            "CERTIFIED_SAT",
            "CERTIFIED_UNSAT",
        }
        by_arm[arm].append(1.0 if verified else 0.0)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 3.5))
    arms = sorted(by_arm, key=lambda arm: (_ARM_ORDER.get(arm, 999), arm))
    values = [mean(by_arm[arm]) if by_arm[arm] else 0.0 for arm in arms]
    ax.bar(range(len(arms)), values, color="#355C7D")
    ax.set_xticks(range(len(arms)), [arm.replace("_", "\n") for arm in arms])
    ax.set_ylabel("Verified solve rate")
    ax.set_ylim(0, 1)
    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def plot_convergence_by_round(records: Sequence[dict], output_path: Path) -> None:
    """Plot solved-within-round curves per arm."""

    by_arm: dict[str, List[dict]] = defaultdict(list)
    for record in records:
        by_arm[str(record.get("arm") or "unknown")].append(record)

    max_rounds = max((int(record.get("max_rounds", 1) or 1) for record in records), default=1)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 3.5))

    for arm, arm_records in sorted(
        by_arm.items(), key=lambda item: (_ARM_ORDER.get(item[0], 999), item[0])
    ):
        xs = list(range(1, max_rounds + 1))
        ys = []
        for round_index in xs:
            solved = sum(
                1
                for record in arm_records
                if str(record.get("verified_outcome"))
                in {"CERTIFIED_SAT", "CERTIFIED_UNSAT"}
                and int(record.get("iterations", 0) or 0) <= round_index
            )
            ys.append(solved / len(arm_records) if arm_records else 0.0)
        ax.plot(xs, ys, marker="o", label=arm.replace("_", " "))

    ax.set_xlabel("Round")
    ax.set_ylabel("Solved within round")
    ax.set_ylim(0, 1)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def plot_efficiency_frontier(records: Sequence[dict], output_path: Path) -> None:
    """Plot mean solver calls against verified solve rate per arm."""

    by_arm: dict[str, List[dict]] = defaultdict(list)
    for record in records:
        by_arm[str(record.get("arm") or "unknown")].append(record)

    points = []
    for arm, arm_records in sorted(
        by_arm.items(), key=lambda item: (_ARM_ORDER.get(item[0], 999), item[0])
    ):
        solve_rate = mean(
            1.0
            if str(record.get("verified_outcome"))
            in {"CERTIFIED_SAT", "CERTIFIED_UNSAT"}
            else 0.0
            for record in arm_records
        )
        mean_solver_calls = mean(float(record.get("solver_calls", 0.0) or 0.0) for record in arm_records)
        points.append((arm, mean_solver_calls, solve_rate))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 3.5))
    for arm, solver_calls, solve_rate in points:
        ax.scatter([solver_calls], [solve_rate], s=70)
        ax.annotate(arm, (solver_calls, solve_rate), fontsize=8, xytext=(5, 3), textcoords="offset points")
    ax.set_xlabel("Mean solver calls")
    ax.set_ylabel("Verified solve rate")
    ax.set_ylim(0, 1)
    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


__all__ = [
    "load_records_from_runs",
    "plot_arm_verified_solve_rate",
    "plot_convergence_by_round",
    "plot_efficiency_frontier",
]
