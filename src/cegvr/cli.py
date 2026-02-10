"""Typer-powered command line interface for CEGVR."""

from __future__ import annotations

import json
from pathlib import Path
import os

import typer
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel

from . import __version__
from .config import DEFAULT_CONFIG_PATH, AppConfig, load_config
from .data.loader import load_jsonl_problems, summarize_by_task
from .engine.configs import ExperimentConfig
from .engine.metrics import compute_metrics
from .engine.repair import repair_until_certified
from .eval.aggregate import aggregate_runs
from .eval.harness import run_evaluation
from .generation.provider import StubGenerator, TraceGenerator
from .generation.llm_linear import LLMLinearGenerator
from .generation.llm_sudoku import LLMSudoku4Generator
from .generation.llm_latin5 import LLMLatin5Generator
from cegvr.plots.curves import (
    load_records_from_runs,
    plot_certification_vs_budget,
    plot_iterations_histogram,
    plot_latency_accuracy_pareto,
)
from cegvr.tables.main import (
    generate_ablation_table,
    generate_main_table,
    generate_main_table_tex,
)
from .report.case_studies import export_case_studies
from .robustness.runner import (
    aggregate_deltas,
    evaluate_variants,
    load_problems,
    save_delta_plot,
    save_delta_table,
    write_results,
)
from .utils.logging import setup_logging
from .utils.random import seed_everything

app = typer.Typer(
    name="cegvr", help="CEGVR toolkit for counterexample-guided, verifiable reasoning."
)
console = Console()

_TOY_PROBLEM_SPEC = {
    "problem_id": "toy-balance",
    "task": "math",
    "variables": [
        {"name": "x", "domain": "int", "bounds": {"lower": 0, "upper": 5}},
        {"name": "y", "domain": "int", "bounds": {"lower": 1, "upper": 6}},
        {"name": "flag", "domain": "bool"},
    ],
    "constraints": [
        {
            "kind": "linear_ineq",
            "terms": [
                {"variable": "x", "coefficient": 1},
                {"variable": "y", "coefficient": 1},
            ],
            "relation": "<=",
            "rhs": 10,
        }
    ],
}


@app.callback()
def main(
    verbose: int = typer.Option(
        0,
        "--verbose",
        "-v",
        count=True,
        help="Increase log verbosity (-v for INFO, -vv for DEBUG).",
    ),
) -> None:
    """Configure logging before executing any command."""

    setup_logging(verbosity=verbose)


@app.command()
def show_config(
    config: Path = typer.Option(
        DEFAULT_CONFIG_PATH,
        "--config",
        "-c",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to a YAML configuration file.",
        show_default=True,
    ),
) -> None:
    """Load a configuration file and display its parsed contents."""

    settings: AppConfig = load_config(config)
    seed_everything(settings.app.seed)
    console.print(f"[bold green]Loaded configuration:[/bold green] {config}")
    console.print(Syntax(settings.yaml(), "yaml"))


@app.command()
def init(
    destination: Path = typer.Option(
        Path("configs/default.yaml"),
        "--copy-to",
        "-o",
        dir_okay=False,
        help="Destination path for a copy of the default configuration.",
        show_default=True,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite the destination if it already exists.",
    ),
) -> None:
    """Copy the built-in default configuration to a new location."""

    if destination.exists() and not force:
        typer.echo(
            f"{destination} already exists. Use --force to overwrite.",
            err=True,
        )
        raise typer.Exit(code=1)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    console.print(
        f"[bold green]Default configuration copied to:[/bold green] {destination}"
    )


@app.command()
def version() -> None:
    """Print the installed toolkit version."""

    console.print(f"CEGVR version {__version__}")


@app.command("gen-toy")
def generate_toy(
    n: int = typer.Option(
        10, "--n", min=1, help="Number of candidate traces to generate."
    ),
    out: Path = typer.Option(
        Path("data/toy/generated.jsonl"),
        "--out",
        dir_okay=False,
        help="Destination JSON Lines file for generated traces.",
        show_default=True,
    ),
) -> None:
    """Generate toy candidate traces using the stub generator."""

    generator = StubGenerator()
    traces = generator.propose(_TOY_PROBLEM_SPEC, budget=n)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for trace in traces:
            handle.write(json.dumps(trace, sort_keys=True))
            handle.write("\n")
    console.print(f"[bold green]Wrote {len(traces)} traces to {out}[/bold green]")


@app.command("solve-toy")
def solve_toy(
    problems: Path = typer.Option(
        Path("data/toy/problems.jsonl"),
        "--problems",
        exists=True,
        readable=True,
        help="JSONL file describing toy problems to solve.",
        show_default=True,
    ),
    out: Path = typer.Option(
        Path("runs/toy/results.jsonl"),
        "--out",
        dir_okay=False,
        help="Destination JSONL file for repair outcomes.",
        show_default=True,
    ),
    max_rounds: int = typer.Option(
        5, "--max-rounds", min=1, help="Maximum repair rounds."
    ),
    budget: int = typer.Option(2, "--budget", min=1, help="Candidates per round."),
    timeout_ms: int = typer.Option(
        2000, "--timeout-ms", min=1, help="Solver timeout per check in ms."
    ),
) -> None:
    """Solve toy problems using the repair loop and stub generator."""

    generator = StubGenerator()
    results: list[dict] = []
    out.parent.mkdir(parents=True, exist_ok=True)

    with (
        problems.open("r", encoding="utf-8") as source,
        out.open("w", encoding="utf-8") as sink,
    ):
        for raw_line in source:
            line = raw_line.strip()
            if not line:
                continue
            problem_spec = json.loads(line)
            outcome = repair_until_certified(
                problem_spec,
                generator,
                max_rounds=max_rounds,
                per_round_budget=budget,
                timeout_ms=timeout_ms,
            )
            record = {
                "problem_id": problem_spec.get("problem_id"),
                "ground_truth": problem_spec.get("ground_truth"),
                **outcome,
            }
            results.append(record)
            sink.write(json.dumps(record, sort_keys=True))
            sink.write("\n")

    metrics = compute_metrics(results)
    console.print(f"[bold green]Processed {len(results)} problems[/bold green]")
    console.print(Syntax(json.dumps(metrics, indent=2, sort_keys=True), "json"))


@app.command("data-stats")
def data_stats(
    path: Path = typer.Option(
        Path("data/toy/problems.jsonl"),
        "--path",
        exists=True,
        readable=True,
        help="JSONL dataset to summarise.",
        show_default=True,
    ),
) -> None:
    """Print basic statistics about a JSONL dataset."""

    problems = load_jsonl_problems(path)
    summary = summarize_by_task(problems)
    payload = {
        "path": str(path),
        "count": len(problems),
        "per_task": summary,
    }
    console.print(Syntax(json.dumps(payload, indent=2, sort_keys=True), "json"))


@app.command("eval")
def eval_dataset(
    problems: Path = typer.Option(
        Path("data/toy/problems.jsonl"),
        "--problems",
        exists=True,
        readable=True,
        help="JSONL dataset to evaluate.",
        show_default=True,
    ),
    out: Path = typer.Option(
        Path("runs/toy"),
        "--out",
        dir_okay=True,
        help="Output directory for evaluation runs.",
        show_default=True,
    ),
    seeds: int = typer.Option(3, "--seeds", min=1, help="Number of random seeds."),
    max_rounds: int = typer.Option(5, "--max-rounds", min=1, help="Repair loop depth."),
    budget: int = typer.Option(2, "--budget", min=1, help="Candidates per iteration."),
    timeout_ms: int = typer.Option(
        2000, "--timeout-ms", min=1, help="SMT timeout per check."
    ),
    no_grammar: bool = typer.Option(
        False, "--no-grammar", help="Disable schema/grammar validation."
    ),
    no_solver: bool = typer.Option(
        False, "--no-solver", help="Skip SMT solving and use baseline."
    ),
    no_repair: bool = typer.Option(
        False, "--no-repair", help="Disable iterative repair beyond first round."
    ),
    generator_name: str = typer.Option(
        "stub",
        "--generator",
        help="Trace generator backend (stub, llm, llm-sudoku).",
    ),
    llm_endpoint: str = typer.Option(
        "http://127.0.0.1:8000/v1/chat/completions",
        "--llm-endpoint",
        help="Local LLM HTTP endpoint.",
        show_default=True,
    ),
    llm_model: str = typer.Option(
        "llama-3-8b-instruct",
        "--llm-model",
        help="LLM model identifier for chat completion API.",
        show_default=True,
    ),
) -> None:
    """Run the evaluation harness over a dataset."""

    gname = generator_name.lower()
    if gname == "llm":
        generator: TraceGenerator = LLMLinearGenerator(
            endpoint=llm_endpoint, model=llm_model
        )
    elif gname == "llm-sudoku":
        generator = LLMSudoku4Generator(endpoint=llm_endpoint, model=llm_model)
    elif gname == "llm-latin5":
        generator = LLMLatin5Generator(endpoint=llm_endpoint, model=llm_model)
    else:
        generator = StubGenerator()
    seed_values = list(range(seeds))
    config = ExperimentConfig.from_flags(
        no_grammar=no_grammar, no_solver=no_solver, no_repair=no_repair
    )
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
    console.print(f"[bold green]Evaluation outputs written to {out}[/bold green]")


@app.command("summarize")
def summarize_runs(
    runs: Path = typer.Option(
        Path("runs/toy"),
        "--runs",
        exists=True,
        file_okay=False,
        help="Directory of evaluation run JSONL files.",
        show_default=True,
    ),
    table: Path = typer.Option(
        Path("tables/main_results.csv"),
        "--table",
        dir_okay=False,
        help="Destination CSV for aggregated metrics.",
        show_default=True,
    ),
) -> None:
    """Aggregate evaluation runs and save metrics table."""

    run_files = sorted(runs.glob("seed_*.jsonl"))
    summary = aggregate_runs(run_files)

    table.parent.mkdir(parents=True, exist_ok=True)
    with table.open("w", encoding="utf-8") as handle:
        handle.write("metric,value,lower,upper\n")
        for name, payload in summary.items():
            if (
                isinstance(payload, dict)
                and {"value", "lower", "upper"} <= payload.keys()
            ):
                handle.write(
                    f"{name},{payload['value']:.4f},{payload['lower']:.4f},{payload['upper']:.4f}\n"
                )

    console.print(Syntax(json.dumps(summary, indent=2, sort_keys=True), "json"))


@app.command("make-figures")
def make_figures(
    runs: Path = typer.Option(
        Path("runs/toy"),
        "--runs",
        exists=True,
        file_okay=False,
        help="Directory of evaluation runs (seed_*.jsonl).",
        show_default=True,
    ),
    out: Path = typer.Option(
        Path("examples/paper_assets/figures"),
        "--out",
        dir_okay=True,
        help="Destination directory for generated figures.",
        show_default=True,
    ),
) -> None:
    """Generate paper-ready figures from evaluation runs."""

    run_files = sorted(runs.glob("seed_*.jsonl"))
    records = load_records_from_runs(run_files)
    if not records:
        typer.echo("No run records found; skipping figure generation.", err=True)
        raise typer.Exit(code=1)

    out.mkdir(parents=True, exist_ok=True)
    plot_certification_vs_budget(records, out / "cert_vs_budget.png")
    plot_iterations_histogram(records, out / "iterations_hist.png")
    plot_latency_accuracy_pareto(records, out / "latency_vs_accuracy.png")
    console.print(f"[bold green]Figures written to {out}[/bold green]")


@app.command("make-tables")
def make_tables(
    runs: Path = typer.Option(
        Path("runs/toy"),
        "--runs",
        exists=True,
        file_okay=False,
        help="Directory of evaluation runs (seed_*.jsonl).",
        show_default=True,
    ),
    out: Path = typer.Option(
        Path("examples/paper_assets/tables"),
        "--out",
        dir_okay=True,
        help="Destination directory for generated tables.",
        show_default=True,
    ),
    latex_dir: Path = typer.Option(
        Path("examples/paper_assets/latex/tables"),
        "--latex",
        dir_okay=True,
        help="Destination directory for LaTeX snippets.",
        show_default=True,
    ),
) -> None:
    """Generate paper-ready tables from evaluation runs."""

    out.mkdir(parents=True, exist_ok=True)
    main_csv = out / "main_results.csv"
    ablations_csv = out / "ablations.csv"
    generate_main_table(runs, main_csv)
    generate_ablation_table(runs, ablations_csv)
    latex_dir.mkdir(parents=True, exist_ok=True)
    latex_root = latex_dir.parent
    csv_reference = Path(os.path.relpath(main_csv, start=latex_root)).as_posix()
    generate_main_table_tex(latex_dir / "table_main.tex", csv_reference=csv_reference)
    console.print(f"[bold green]Tables written to {out}[/bold green]")
    console.print(
        f"[bold green]LaTeX snippet written to {latex_dir / 'table_main.tex'}[/bold green]"
    )


@app.command("explain")
def explain(
    problem_id: str = typer.Option(
        ..., "--problem-id", help="Problem identifier to inspect."
    ),
    runs_path: Path = typer.Option(
        Path("runs/toy/results.jsonl"),
        "--from",
        exists=True,
        readable=True,
        help="JSONL file containing evaluation results.",
        show_default=True,
    ),
) -> None:
    """Print diagnostics for a single evaluated problem."""

    target_record: dict | None = None
    with runs_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if str(record.get("problem_id")) == problem_id:
                target_record = record
                break

    if target_record is None:
        typer.echo(f"Problem '{problem_id}' not found in {runs_path}", err=True)
        raise typer.Exit(code=1)

    panels = []
    panels.append(
        Panel.fit(
            Syntax(
                json.dumps(target_record.get("trace", {}), indent=2, sort_keys=True),
                "json",
            ),
            title="Certified Trace",
        )
    )
    panels.append(
        Panel.fit(
            Syntax(
                json.dumps(target_record.get("model", {}), indent=2, sort_keys=True),
                "json",
            ),
            title="Model",
        )
    )
    panels.append(
        Panel.fit(
            Syntax(
                json.dumps(target_record.get("history", []), indent=2, sort_keys=True),
                "json",
            ),
            title="History",
        )
    )
    if target_record.get("feedback"):
        panels.append(
            Panel.fit(
                Syntax(
                    json.dumps(target_record["feedback"], indent=2, sort_keys=True),
                    "json",
                ),
                title="Feedback",
            )
        )

    console.print(
        f"[bold cyan]Pipeline explanation for problem {problem_id}[/bold cyan]"
    )
    for panel in panels:
        console.print(panel)


@app.command("export-cases")
def export_cases(
    runs: Path = typer.Option(
        Path("runs/toy"),
        "--runs",
        exists=True,
        file_okay=False,
        help="Directory containing evaluation runs (seed_*.jsonl).",
        show_default=True,
    ),
    problems: Path = typer.Option(
        Path("data/toy/problems.jsonl"),
        "--problems",
        exists=True,
        readable=True,
        help="Original problems JSONL.",
        show_default=True,
    ),
    out: Path = typer.Option(
        Path("reports/case_studies.md"),
        "--out",
        dir_okay=False,
        help="Destination Markdown file.",
        show_default=True,
    ),
    n: int = typer.Option(
        4, "--n", min=1, help="Number of SAT and UNSAT cases to include."
    ),
) -> None:
    """Export case studies for the appendix."""

    export_case_studies(run_dir=runs, problems_path=problems, output_path=out, n=n)
    console.print(f"[bold green]Case studies written to {out}[/bold green]")


@app.command("robustness")
def robustness(
    problems: Path = typer.Option(
        Path("data/toy/problems.jsonl"),
        "--problems",
        exists=True,
        readable=True,
        help="Base problems JSONL file.",
        show_default=True,
    ),
    out: Path = typer.Option(
        Path("runs/robust"),
        "--out",
        dir_okay=True,
        help="Output directory for robustness evaluation.",
        show_default=True,
    ),
    variants: int = typer.Option(
        3, "--variants", min=0, help="Number of spec variants per problem."
    ),
    no_solver: bool = typer.Option(
        False, "--no-solver", help="Disable solver during robustness runs."
    ),
) -> None:
    """Run robustness evaluation across paraphrases and spec variants."""

    generator = StubGenerator()
    config = ExperimentConfig.from_flags(no_solver=no_solver)
    problems_list = load_problems(problems)
    results = evaluate_variants(
        problems_list, variants=variants, generator=generator, config=config
    )
    write_results(results, out)
    deltas = aggregate_deltas(results)
    tables_dir = out / "tables"
    figures_dir = out / "figures"
    save_delta_table(deltas, tables_dir / "robustness.csv")
    save_delta_plot(deltas, figures_dir / "fig_robustness.png")
    save_delta_table(deltas, Path("tables/robustness.csv"))
    save_delta_plot(deltas, Path("fig_robustness.png"))
    console.print(f"[bold green]Robustness outputs written to {out}[/bold green]")


def app_entry() -> None:
    """Entry point compatible with console_scripts."""

    app()


__all__ = ["app", "app_entry"]
