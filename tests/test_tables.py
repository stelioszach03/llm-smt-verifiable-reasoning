"""Tests for table generation utilities and CLI integration."""

from __future__ import annotations

import json
import csv
from pathlib import Path

from typer.testing import CliRunner

from cegvr.cli import app
from cegvr.tables.main import generate_main_table, generate_main_table_tex


def _write_run(tmp_path: Path) -> Path:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    run_file = runs_dir / "seed_0.jsonl"
    records = [
        {
            "certified": True,
            "uncertified_correct": False,
            "iterations": 2,
            "latency_ms": 1.5,
            "task": "math",
        },
        {
            "certified": False,
            "uncertified_correct": True,
            "iterations": 3,
            "latency_ms": 2.5,
            "task": "planning",
        },
    ]
    with run_file.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record))
            handle.write("\n")
    return runs_dir


def test_generate_main_table_writes_csv(tmp_path: Path) -> None:
    runs_dir = _write_run(tmp_path)
    csv_path = tmp_path / "tables" / "main_results.csv"
    rows = generate_main_table(runs_dir, csv_path)

    assert csv_path.exists()
    assert rows[0]["metric"] == "certified_accuracy"

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        entries = list(reader)

    assert entries[0]["metric"] == "certified_accuracy"
    assert any(entry["metric"].startswith("count_") for entry in entries)


def test_make_tables_cli_creates_latex_snippet(tmp_path: Path) -> None:
    runs_dir = _write_run(tmp_path)
    out_dir = tmp_path / "tables"
    latex_dir = tmp_path / "latex" / "tables"

    result = CliRunner().invoke(
        app,
        [
            "make-tables",
            "--runs",
            str(runs_dir),
            "--out",
            str(out_dir),
            "--latex",
            str(latex_dir),
        ],
    )

    assert result.exit_code == 0, result.stdout

    latex_path = latex_dir / "table_main.tex"
    assert latex_path.exists()

    content = latex_path.read_text(encoding="utf-8")
    assert "pgfplotstabletypeset" in content
    assert "../tables/main_results.csv" in content

    csv_path = out_dir / "main_results.csv"
    assert csv_path.exists()


def test_generate_main_table_tex_overwrites_target(tmp_path: Path) -> None:
    tex_path = tmp_path / "latex" / "tables" / "table_main.tex"
    tex_path.parent.mkdir(parents=True)
    tex_path.write_text("old", encoding="utf-8")

    generate_main_table_tex(tex_path, csv_reference="rel/path.csv")

    content = tex_path.read_text(encoding="utf-8")
    assert "rel/path.csv" in content
    assert "old" not in content
