"""Synthetic transform-only fixtures; no figures or experimental evidence produced."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "pilot_plots",
    Path(__file__).resolve().parents[1] / "scripts/plot_openrouter_pilot.py",
)
plots = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plots)


def synthetic_analysis():
    rows = []
    for stratum, planned, observed, success in [
        ("sat", 9, 3, 2),
        ("unsat", 6, 0, 0),
        ("all", 15, 3, 2),
    ]:
        rows.append(
            {
                "arm": "one_shot",
                "stratum": stratum,
                "planned": planned,
                "observed": observed,
                "certified_successes": success,
                "unlaunched_missing": planned - observed,
                "observed_success_rate": success / observed if observed else None,
                "mean_accounted_cost_usd_per_observed_episode": 0.001
                if observed
                else None,
                "status_counts": {"complete": observed},
            }
        )
    return {
        "fixture_only": True,
        "schema": "cegvr-openrouter-pilot-analysis-v1",
        "summary": rows,
        "planned": 15,
        "observed": 3,
        "study_status": "stopped",
    }


def test_partial_fixture_keeps_dynamic_denominators_and_missing_separate():
    data = plots.plot_data(synthetic_analysis())
    assert data["partial"] and data["title_prefix"] == "PARTIAL MATRIX"
    assert data["coverage"] == "3/15 episodes recorded"
    sat = data["groups"][("one_shot", "sat")]
    unsat = data["groups"][("one_shot", "unsat")]
    assert sat["coverage_label"] == "3/9"
    assert sat["successes"] == 2 and sat["observed_unsuccessful"] == 1
    assert sat["unlaunched_missing"] == 6
    assert unsat["coverage_label"] == "0/6" and unsat["success_percent"] is None


def test_unobserved_or_inconsistent_metrics_cannot_be_plot_defaults():
    report = synthetic_analysis()
    report["summary"][1]["observed_success_rate"] = 0
    with pytest.raises(ValueError, match="must remain null"):
        plots.plot_data(report)
    report = synthetic_analysis()
    report["summary"][0]["certified_successes"] = 3
    with pytest.raises(ValueError, match="denominator"):
        plots.plot_data(report)
    report = synthetic_analysis()
    report["planned"] = 750
    with pytest.raises(ValueError, match="overall analysis matrix"):
        plots.plot_data(report)


@pytest.mark.parametrize("execution_status", ["incomplete", "stopped"])
def test_complete_matrix_is_distinct_from_non_normal_execution_status(execution_status):
    report = synthetic_analysis()
    for row in report["summary"]:
        row.update(
            observed=row["planned"],
            certified_successes=row["planned"],
            unlaunched_missing=0,
            observed_success_rate=1,
            mean_accounted_cost_usd_per_observed_episode=0.001,
            status_counts={"complete": row["planned"]},
        )
    report["observed"] = report["planned"]
    report["study_status"] = execution_status
    data = plots.plot_data(report)
    assert not data["partial"]
    assert data["title_prefix"] == "COMPLETED MATRIX"
    assert not data["all_episodes_ended_normally"]
    assert f"Execution status: {execution_status}" in data["execution_disclosure"]
    report["study_status"] = "complete"
    assert plots.plot_data(report)["all_episodes_ended_normally"]


def test_750_recorded_fixture_with_one_operational_stop_is_not_all_normal_execution():
    rows = []
    for arm in plots.NAMES:
        for stratum, planned in (("sat", 90), ("unsat", 60), ("all", 150)):
            stopped = int(arm == "one_shot" and stratum in ("sat", "all"))
            rows.append(
                {
                    "arm": arm,
                    "stratum": stratum,
                    "planned": planned,
                    "observed": planned,
                    "certified_successes": planned - stopped,
                    "unlaunched_missing": 0,
                    "observed_success_rate": (planned - stopped) / planned,
                    "mean_accounted_cost_usd_per_observed_episode": 0.001,
                    "status_counts": {
                        "complete": planned - stopped,
                        "stopped": stopped,
                    },
                }
            )
    report = {
        "fixture_only": True,
        "schema": "cegvr-openrouter-pilot-analysis-v1",
        "summary": rows,
        "planned": 750,
        "observed": 750,
        "study_status": "complete",
        "recorded_status_counts": {"complete": 749, "stopped": 1, "error": 0},
        "post_freeze_operational_extension": True,
        "operational_amendment_sha256": "a" * 64,
        "original_admission_seconds": 2700,
        "additional_admission_seconds": 2700,
    }
    data = plots.plot_data(report)
    assert not data["partial"]
    assert data["title_prefix"] == "COMPLETED MATRIX"
    assert data["coverage"] == "750/750 episodes recorded"
    assert not data["all_episodes_ended_normally"]
    assert data["operational_stopped"] == 1 and data["operational_errors"] == 0
    assert "Operational stops/errors: 1/0" in data["execution_disclosure"]
    assert "not attributed to model quality" in data["execution_disclosure"]
    assert "Post-freeze operational extension" in data["execution_disclosure"]
    assert "2700 + 2700" in data["execution_disclosure"]
    report["study_status"] = "incomplete"
    data = plots.plot_data(report)
    assert not data["partial"]
    assert data["title_prefix"] == "COMPLETED MATRIX"
    assert data["coverage"] == "750/750 episodes recorded"
    assert not data["all_episodes_ended_normally"]
