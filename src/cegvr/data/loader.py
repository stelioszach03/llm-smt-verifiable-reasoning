"""Utilities for loading toy reasoning problems from JSONL files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, Iterator, List

VALID_TASKS = {"math", "scheduling", "planning"}


def load_jsonl_problems(path: Path | str) -> List[Dict]:
    """Load a JSON Lines file containing reasoning problem definitions."""

    return list(iter_jsonl_problems(path))


def iter_jsonl_problems(path: Path | str) -> Iterator[Dict]:
    """Yield problem dictionaries from a JSONL file."""

    target = Path(path)
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            problem = json.loads(line)
            yield problem


def filter_by_task(problems: Iterable[Dict], task: str) -> List[Dict]:
    """Return problems matching the requested task type."""

    if task not in VALID_TASKS:
        raise ValueError(
            f"Unknown task '{task}'. Expected one of {sorted(VALID_TASKS)}"
        )
    return [problem for problem in problems if problem.get("task") == task]


def summarize_by_task(problems: Iterable[Dict]) -> Dict[str, int]:
    """Compute a task frequency summary."""

    counts = {task: 0 for task in VALID_TASKS}
    for problem in problems:
        task = problem.get("task")
        if task in counts:
            counts[task] += 1
    return counts


__all__ = [
    "load_jsonl_problems",
    "iter_jsonl_problems",
    "filter_by_task",
    "summarize_by_task",
    "VALID_TASKS",
]
