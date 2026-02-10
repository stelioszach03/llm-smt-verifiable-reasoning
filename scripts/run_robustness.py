"""Run robustness evaluation using problem variants."""

from __future__ import annotations

from pathlib import Path

import typer

from cegvr.engine.configs import ExperimentConfig
from cegvr.generation.provider import StubGenerator
from cegvr.robustness.runner import (
    aggregate_deltas,
    evaluate_variants,
    load_problems,
    save_delta_plot,
    save_delta_table,
    write_results,
)

app = typer.Typer(help="Robustness evaluation harness.")


def main(
    problems: Path = typer.Option(..., exists=True, readable=True, help="Base problems JSONL."),
    out: Path = typer.Option(Path("runs/robust"), dir_okay=True, help="Output directory."),
    variants: int = typer.Option(3, min=0, help="Number of spec variants per problem."),
    no_solver: bool = typer.Option(False, "--no-solver", help="Disable solver calls for baseline evaluation."),
) -> None:
    generator = StubGenerator()
    config = ExperimentConfig.from_flags(no_solver=no_solver)
    problems_list = load_problems(problems)
    results = evaluate_variants(problems_list, variants=variants, generator=generator, config=config)
    write_results(results, out)

    deltas = aggregate_deltas(results)
    tables_dir = out / "tables"
    figures_dir = out / "figures"
    save_delta_table(deltas, tables_dir / "robustness.csv")
    save_delta_plot(deltas, figures_dir / "fig_robustness.png")
    save_delta_table(deltas, Path("tables/robustness.csv"))
    save_delta_plot(deltas, Path("fig_robustness.png"))
    typer.echo(f"Robustness outputs written to {out}")


if __name__ == "__main__":  # pragma: no cover
    app()
