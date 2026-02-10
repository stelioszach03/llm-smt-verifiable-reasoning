"""Utility functions for summarising repair outcomes."""

from __future__ import annotations

from typing import Any, Dict, Iterable


def compute_metrics(records: Iterable[Dict[str, Any]]) -> Dict[str, float]:
    """Compute aggregate metrics over repair loop results."""

    records_list = list(records)
    total = len(records_list)
    if total == 0:
        return {
            "certified_accuracy": 0.0,
            "uncertified_accuracy": 0.0,
            "avg_iterations": 0.0,
            "avg_latency_ms": 0.0,
            "coverage": 0.0,
        }

    certified = [
        record for record in records_list if record.get("status") == "certified"
    ]
    coverage = len(certified) / total

    avg_iterations = sum(record.get("rounds", 0) for record in records_list) / total
    avg_latency = (
        sum(float(record.get("latency_ms", 0.0)) for record in records_list) / total
    )

    sat_truth = [
        record for record in records_list if record.get("ground_truth") == "sat"
    ]
    unsat_truth = [
        record for record in records_list if record.get("ground_truth") == "unsat"
    ]

    certified_accuracy = (
        sum(1 for record in certified if record.get("ground_truth") == "sat")
        / len(sat_truth)
        if sat_truth
        else 0.0
    )
    uncertified_accuracy = (
        sum(
            1
            for record in records_list
            if record.get("status") != "certified"
            and record.get("ground_truth") == "unsat"
        )
        / len(unsat_truth)
        if unsat_truth
        else 0.0
    )

    return {
        "certified_accuracy": certified_accuracy,
        "uncertified_accuracy": uncertified_accuracy,
        "avg_iterations": avg_iterations,
        "avg_latency_ms": avg_latency,
        "coverage": coverage,
    }


__all__ = ["compute_metrics"]
