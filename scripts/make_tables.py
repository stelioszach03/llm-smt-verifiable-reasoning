"""Script to generate paper tables from evaluation runs."""

from __future__ import annotations

from pathlib import Path
import os

import typer

from cegvr.tables.main import (
    generate_ablation_table,
    generate_main_table,
    generate_main_table_tex,
)

app = typer.Typer(help="Generate tables for paper assets.")


@app.command()
def main(
    runs: Path = typer.Option(..., exists=True, file_okay=False, help="Directory containing run JSONL files."),
    out: Path = typer.Option(Path("examples/paper_assets/tables"), dir_okay=True, help="Output directory for tables."),
    latex_dir: Path = typer.Option(
        Path("examples/paper_assets/latex/tables"),
        dir_okay=True,
        help="Output directory for LaTeX snippets.",
    ),
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    main_csv = out / "main_results.csv"
    ablations_csv = out / "ablations.csv"
    generate_main_table(runs, main_csv)
    generate_ablation_table(runs, ablations_csv)
    latex_dir.mkdir(parents=True, exist_ok=True)
    latex_root = latex_dir.parent
    csv_reference = Path(os.path.relpath(main_csv, start=latex_root)).as_posix()
    generate_main_table_tex(latex_dir / "table_main.tex", csv_reference=csv_reference)
    typer.echo(f"Main table written to {main_csv}")
    typer.echo(f"Ablation table written to {ablations_csv}")
    typer.echo(f"LaTeX snippet written to {latex_dir / 'table_main.tex'}")


if __name__ == "__main__":  # pragma: no cover
    app()
