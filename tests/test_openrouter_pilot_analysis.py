"""Small synthetic accounting fixtures; never experimental model results."""

import importlib.util
from itertools import product
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "openrouter_pilot_analysis",
    Path(__file__).resolve().parents[1] / "scripts/analyze_openrouter_pilot.py",
)
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def fixture_study(root, *, all_records=False):
    tasks = [
        {"problem_id": "sat-task", "ground_truth": "sat"},
        {"problem_id": "unsat-task", "ground_truth": "unsat"},
    ]
    seeds, arms = [17, 29], ["one_shot", "multi_no_feedback"]
    order = [
        {
            "id": f"ep-{i}",
            "problem_id": task["problem_id"],
            "ground_truth": task["ground_truth"],
            "seed": seed,
            "arm": arm,
        }
        for i, (task, seed, arm) in enumerate(product(tasks, seeds, arms))
    ]
    protocol = {
        "selected_tasks": tasks,
        "seeds": seeds,
        "arms": arms,
        "study_order": order,
    }
    rows = []
    for row in order if all_records else order[:-1]:
        outcome = {
            "status": "certified",
            "verified_outcome": "CERTIFIED_SAT"
            if row["ground_truth"] == "sat"
            else "CERTIFIED_UNSAT",
            "predicted_status": row["ground_truth"],
            "witness_policy": "withhold",
            "generated_candidates": [{}, {}, {}, {}],
            "evaluated_candidates": 1,
            "unevaluated_candidates": 3,
            "usage_complete": True,
            "total_tokens": 80,
            "solver_calls": 1,
            "rounds": 1,
        }
        record = {
            **row,
            "status": "complete",
            "outcome": outcome,
            "provider_calls": 4,
            "accounted_cost_usd": 0.01,
            "provider_reported_cost_usd": 0.01,
            "uncertain_calls": 0,
            "transport_errors": 0,
            "wall_latency_ms": 10,
            "error": None,
        }
        path = root / "episodes" / row["id"]
        path.mkdir(parents=True)
        (path / "result.json").write_text(json.dumps(record))
        rows.append(record)
    manifest = {
        "planned": len(order),
        "completed": len(rows),
        "missing": order[len(rows) :],
        "status": "complete" if all_records else "stopped",
    }
    (root / "protocol.json").write_text(json.dumps(protocol))
    (root / "manifest.json").write_text(json.dumps(manifest))
    (root / "direct_solver.json").write_text(
        json.dumps({"control": "fixture-only", "llm_calls": 0})
    )
    return protocol, rows


def save_record(root, record):
    (root / "episodes" / record["id"] / "result.json").write_text(json.dumps(record))


def test_partial_matrix_missing_is_not_zero_and_stopped_error_are_observed_failures(
    tmp_path,
):
    _, rows = fixture_study(tmp_path)
    rows[0].update(
        status="error",
        outcome=None,
        uncertain_calls=1,
        provider_reported_cost_usd=None,
        error="transport_error",
    )
    rows[2].update(status="stopped", outcome=None, error="operational_deadline")
    save_record(tmp_path, rows[0])
    save_record(tmp_path, rows[2])
    report, metrics = analysis.analyze(tmp_path)
    primary = next(
        r for r in report["summary"] if r["stratum"] == "sat" and r["arm"] == "one_shot"
    )
    assert primary["observed"] == primary["planned"] == 2
    assert primary["certified_successes"] == 0
    assert primary["observed_success_rate"] == 0
    assert primary["mean_accounted_cost_per_certified_success"] is None
    secondary = next(
        r
        for r in report["summary"]
        if r["stratum"] == "unsat" and r["arm"] == "multi_no_feedback"
    )
    assert secondary["observed"] == 1 and secondary["planned"] == 2
    assert secondary["observed_success_rate"] == 1
    assert secondary["complete_matrix_success_rate"] is None
    assert secondary["unlaunched_missing"] == 1
    assert len(report["missing"]) == 1
    assert report["confidence_intervals"] is None and not report["significance_claim"]
    assert next(r for r in metrics if r["id"] == rows[0]["id"])["total_tokens"] is None


def test_oracle_satisfiability_without_valid_candidate_is_not_a_success(tmp_path):
    _, rows = fixture_study(tmp_path)
    row = rows[0]
    row["outcome"].update(
        status="failed",
        verified_outcome="FALSE_UNSAT_CLAIM",
        predicted_status="unsat",
        verifier_result="sat",
    )
    assert analysis.metrics(row)["success"] == 0
    row["outcome"]["verified_outcome"] = "CERTIFIED_UNSAT"
    with pytest.raises(ValueError, match="contradicts"):
        analysis.metrics(row)


def test_witness_assistance_and_discarded_candidate_accounting_are_detected(tmp_path):
    _, rows = fixture_study(tmp_path)
    row = rows[0]
    row["outcome"]["witness_policy"] = "include"
    with pytest.raises(ValueError, match="witness policy"):
        analysis.metrics(row)
    row["outcome"]["witness_policy"] = "withhold"
    metric = analysis.metrics(row)
    assert metric["provider_calls"] == 4 and metric["unevaluated_candidates"] == 3
    row["outcome"]["unevaluated_candidates"] = 0
    with pytest.raises(ValueError, match="candidate counts disagree"):
        analysis.metrics(row)


def test_token_unknown_and_unconfirmed_cost_do_not_become_measured_zero(tmp_path):
    _, rows = fixture_study(tmp_path)
    row = rows[0]
    row["outcome"].update(usage_complete=False, total_tokens=None)
    row.update(provider_reported_cost_usd=None, uncertain_calls=1)
    metric = analysis.metrics(row)
    assert metric["total_tokens"] is None
    assert metric["provider_reported_cost_usd"] is None
    assert metric["unconfirmed_reserve_usd"] == 0.01


def test_duplicate_identity_and_manifest_missing_cannot_silently_change_denominators(
    tmp_path,
):
    protocol, _ = fixture_study(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["missing"] = []
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="does not reconcile"):
        analysis.analyze(tmp_path)
    protocol["study_order"].pop()
    (tmp_path / "protocol.json").write_text(json.dumps(protocol))
    with pytest.raises(ValueError, match="Cartesian matrix"):
        analysis.analyze(tmp_path)


def test_pairing_preserves_requested_seeds_but_counts_problems_separately(tmp_path):
    fixture_study(tmp_path, all_records=True)
    report, _ = analysis.analyze(tmp_path)
    pair = next(
        r for r in report["paired_descriptive_comparisons"] if r["stratum"] == "sat"
    )
    assert pair["observed_pairs"] == 2
    assert pair["observed_problems"] == 1
    assert pair["success_rate_difference_a_minus_b"] == 0
    assert pair["mean_accounted_cost_difference_a_minus_b"] == 0


def test_analysis_cli_keeps_source_directory_immutable(tmp_path):
    source = tmp_path / "study"
    source.mkdir()
    fixture_study(source)
    before = {
        str(p.relative_to(source)): p.read_bytes()
        for p in source.rglob("*")
        if p.is_file()
    }
    destination = tmp_path / "analysis"
    assert analysis.main([str(source), "--output", str(destination)]) == 0
    assert (destination / "analysis.json").exists()
    assert before == {
        str(p.relative_to(source)): p.read_bytes()
        for p in source.rglob("*")
        if p.is_file()
    }
    with pytest.raises(SystemExit):
        analysis.main([str(source), "--output", str(source / "analysis")])


def test_worker_error_unknown_wall_time_is_excluded_not_imputed_zero(tmp_path):
    _, rows = fixture_study(tmp_path)
    row = rows[0]
    row.update(
        status="error",
        outcome=None,
        wall_latency_ms=None,
        provider_reported_cost_usd=None,
        error="worker_exception",
    )
    save_record(tmp_path, row)
    report, metrics = analysis.analyze(tmp_path)
    primary = next(
        r for r in report["summary"] if r["stratum"] == "sat" and r["arm"] == "one_shot"
    )
    assert primary["observed"] == 2
    assert primary["episodes_with_measured_wall_latency"] == 1
    assert primary["mean_wall_latency_ms"] == 10
    failed = next(r for r in metrics if r["id"] == row["id"])
    assert (
        failed["wall_latency_ms"] is None
        and failed["provider_reported_cost_usd"] is None
    )
    row.update(status="complete", outcome=rows[2]["outcome"])
    with pytest.raises(ValueError, match="wall_latency_ms"):
        analysis.metrics(row)
