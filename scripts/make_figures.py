"""Script for generating paper figures from evaluation runs."""

from __future__ import annotations

from pathlib import Path

import typer

from cegvr.plots.curves import (
    load_records_from_runs,
    plot_arm_verified_solve_rate,
    plot_convergence_by_round,
    plot_efficiency_frontier,
)

app = typer.Typer(help="Generate plots for paper assets.")


@app.command()
def main(
    runs: Path = typer.Option(..., exists=True, file_okay=False, help="Directory of evaluation runs."),
    out: Path = typer.Option(Path("examples/paper_assets/figures"), dir_okay=True, help="Output directory."),
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    run_files = sorted(runs.rglob("seed_*.jsonl"))
    records = load_records_from_runs(run_files)

    if not records:
        typer.echo("No records found; skipping figure generation.")
        raise typer.Exit(code=1)

    plot_arm_verified_solve_rate(records, out / "arm_verified_solve_rate.png")
    plot_convergence_by_round(records, out / "convergence_by_round.png")
    plot_efficiency_frontier(records, out / "efficiency_frontier.png")
    typer.echo(f"Figures written to {out}")


if __name__ == "__main__":  # pragma: no cover
    app()
