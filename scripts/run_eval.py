"""Command-line entry point for evaluation harness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

import typer

from cegvr.engine.configs import ExperimentConfig
from cegvr.eval.harness import run_evaluation
from cegvr.eval.aggregate import aggregate_runs
from cegvr.generation.provider import StubGenerator

app = typer.Typer(help="Evaluation harness utilities.")


@app.command("run")
def run(
    problems: Path = typer.Option(..., exists=True, readable=True, help="JSONL dataset"),
    out: Path = typer.Option(Path("runs/toy"), dir_okay=True, help="Output directory"),
    seeds: int = typer.Option(3, min=1, help="Number of seeds to run"),
    max_rounds: int = typer.Option(5, min=1),
    budget: int = typer.Option(2, min=1),
    timeout_ms: int = typer.Option(2000, min=1),
    no_grammar: bool = typer.Option(False, "--no-grammar", help="Disable grammar validation"),
    no_solver: bool = typer.Option(False, "--no-solver", help="Skip SMT solving"),
    no_repair: bool = typer.Option(False, "--no-repair", help="Disable iterative repair"),
) -> None:
    generator = StubGenerator()
    seed_values = list(range(seeds))
    config = ExperimentConfig.from_flags(no_grammar=no_grammar, no_solver=no_solver, no_repair=no_repair)
    run_evaluation(
        dataset_path=problems,
        output_path=out,
        generator=generator,
        seeds=seed_values,
        max_rounds=max_rounds,
        per_round_budget=budget,
        timeout_ms=timeout_ms,
        config=config,
    )


@app.command("summarize")
def summarize(
    runs: Path = typer.Option(..., exists=True, file_okay=False, help="Directory of run JSONL files"),
    table: Path = typer.Option(Path("tables/main_results.csv"), dir_okay=False, help="CSV output"),
) -> None:
    run_files: List[Path] = sorted(runs.glob("seed_*.jsonl"))
    summary = aggregate_runs(run_files)
    table.parent.mkdir(parents=True, exist_ok=True)
    with table.open("w", encoding="utf-8") as handle:
        headers = ["metric", "value", "lower", "upper"]
        handle.write(",".join(headers) + "\n")
        for metric_name, payload in summary.items():
            if isinstance(payload, dict) and {"value", "lower", "upper"}.issubset(payload):
                handle.write(
                    f"{metric_name},{payload['value']:.4f},{payload['lower']:.4f},{payload['upper']:.4f}\n"
                )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":  # pragma: no cover
    app()
