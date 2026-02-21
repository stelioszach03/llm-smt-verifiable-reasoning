"""Smoke tests for the CLI interface."""

from typer.testing import CliRunner

from cegvr.cli import app


def test_cli_help() -> None:
    """The top-level help command should execute without errors."""

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "CEGVR" in result.output


def test_eval_help_mentions_cd_vgs_arm() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["eval", "--help"])
    assert result.exit_code == 0
    assert "cd_vgs_core_rank" in result.output
