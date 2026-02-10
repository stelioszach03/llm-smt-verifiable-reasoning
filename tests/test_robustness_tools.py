"""Tests for robustness utilities."""

from __future__ import annotations

from pathlib import Path

from cegvr.engine.configs import ExperimentConfig
from cegvr.generation.provider import StubGenerator
from cegvr.robustness.paraphrase import paraphrase_problem, paraphrase_statement
from cegvr.robustness.runner import (
    aggregate_deltas,
    evaluate_variants,
    save_delta_plot,
    save_delta_table,
)
from cegvr.robustness.spec_variations import generate_variants

BASE_PROBLEM = {
    "problem_id": "p1",
    "task": "math",
    "variables": [{"name": "x", "domain": "int", "bounds": {"lower": 0, "upper": 5}}],
    "constraints": [],
    "ground_truth": "sat",
}


def test_paraphrase_changes_text() -> None:
    text = "sum must be at least 5"
    paraphrased = paraphrase_statement(text)
    assert paraphrased != text

    problem = {"description": "difference at most zero"}
    rewritten = paraphrase_problem(problem)
    assert rewritten["description"] != problem["description"]


def test_generate_variants_produces_variations() -> None:
    variants = generate_variants(BASE_PROBLEM, 3)
    assert len(variants) == 3
    assert (
        variants[0]["variables"][0]["bounds"]["lower"]
        != BASE_PROBLEM["variables"][0]["bounds"]["lower"]
    )


def test_evaluate_variants_and_aggregate(tmp_path: Path) -> None:
    generator = StubGenerator(seed=0)
    config = ExperimentConfig.from_flags(no_solver=True)
    results = evaluate_variants(
        [BASE_PROBLEM], variants=2, generator=generator, config=config
    )
    deltas = aggregate_deltas(results)
    assert set(deltas) == {"base", "paraphrase", "spec_0", "spec_1"}

    table_path = tmp_path / "robust.csv"
    plot_path = tmp_path / "robust.png"
    save_delta_table(deltas, table_path)
    save_delta_plot(deltas, plot_path)
    assert table_path.exists()
    assert plot_path.exists()
