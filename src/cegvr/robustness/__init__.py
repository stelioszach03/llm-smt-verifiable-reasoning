"""Robustness evaluation utilities."""

from .paraphrase import paraphrase_problem, paraphrase_statement
from .spec_variations import generate_variants, perturb_bounds, vary_objective
from .runner import (
    load_problems,
    evaluate_variants,
    write_results,
    aggregate_deltas,
    save_delta_plot,
    save_delta_table,
)

__all__ = [
    "paraphrase_problem",
    "paraphrase_statement",
    "generate_variants",
    "perturb_bounds",
    "vary_objective",
    "load_problems",
    "evaluate_variants",
    "write_results",
    "aggregate_deltas",
    "save_delta_plot",
    "save_delta_table",
]
