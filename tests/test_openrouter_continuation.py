"""Synthetic local evidence only; no provider calls or running-study changes."""

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from concurrent.futures import Future
from types import ModuleType
from types import SimpleNamespace

import pytest


source = Path(__file__).resolve().parents[1] / "scripts/continue_openrouter_pilot.py"
spec = importlib.util.spec_from_file_location("continuation", source)
continuation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(continuation)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def protocol():
    tasks = [
        {"problem_id": f"fixture-{i}", "ground_truth": "sat" if i < 30 else "unsat"}
        for i in range(50)
    ]
    arms = [
        "one_shot",
        "multi_no_feedback",
        "multi_generic_feedback",
        "multi_unsat_core_feedback",
        "cd_vgs_core_rank",
    ]
    rows = []
    for task in tasks:
        for seed in (17, 29, 43):
            for arm in arms:
                ident = hashlib.sha256(
                    f"{task['problem_id']}|{seed}|{arm}".encode()
                ).hexdigest()[:20]
                rows.append({**task, "seed": seed, "arm": arm, "id": ident})
    return {
        "source_commit": continuation.SOURCE_COMMIT,
        "study_id": continuation.STUDY_ID,
        "model": continuation.MODEL,
        "provider": {
            "only": ["coreweave/fp4"],
            "quantizations": ["fp4"],
            "allow_fallbacks": False,
        },
        "temperature": 0.2,
        "max_output_tokens": 2048,
        "max_rounds": 4,
        "per_round_candidates": 4,
        "solver_timeout_ms": 1500,
        "witness_policy": "withhold",
        "allowance_usd": 3.0,
        "workers": 8,
        "operational_seconds": 2700,
        "seeds": [17, 29, 43],
        "selected_tasks": tasks,
        "arms": arms,
        "study_order": rows,
    }


def fixture_study(tmp_path, *, observed=2):
    study = tmp_path / "study"
    study.mkdir()
    plan = protocol()
    save(study / "protocol.json", plan)
    save(study / "direct_solver.json", {"provider_calls": 0, "rows": []})
    began = 1_800_000_000
    for index, row in enumerate(plan["study_order"][:observed]):
        record = {
            **row,
            "status": "stopped" if index == 0 else "complete",
            "error": "StudyStopped" if index == 0 else None,
            "outcome": None,
            "provider_calls": 0,
            "accounted_cost_usd": 0.0,
            "finished_at": iso(began + 2710),
        }
        save(study / "episodes" / row["id"] / "result.json", record)
    manifest = {
        "status": "incomplete",
        "started_at": iso(began),
        "finished_at": iso(began + 2720),
        "elapsed_seconds": 2720,
        "protocol_sha256": continuation.sha(study / "protocol.json"),
        "planned": 750,
        "completed": observed,
        "missing": plan["study_order"][observed:],
        "budget_before": {"charged_usd": 1.0},
    }
    save(study / "manifest.json", manifest)
    ledger = {
        "study_accounted_micro_usd": 0,
        "research_charged_micro_usd": 1_000_000,
        "research_remaining_micro_usd": 10_000_000,
        "disabled": False,
        "by_run": {},
        "ledger_identity_sha256": "fixture-ledger",
    }
    return study, plan, manifest, ledger


def test_only_original_unlaunched_cells_eligible_and_stopped_row_unchanged(tmp_path):
    study, plan, manifest, ledger = fixture_study(tmp_path)
    before = (
        study / "episodes" / plan["study_order"][0]["id"] / "result.json"
    ).read_bytes()
    records, missing, hashes = continuation.eligibility(study, plan, manifest, ledger)
    assert len(records) == 2 and len(missing) == 748
    assert missing == plan["study_order"][2:]
    assert records[plan["study_order"][0]["id"]]["status"] == "stopped"
    assert (
        study / "episodes" / plan["study_order"][0]["id"] / "result.json"
    ).read_bytes() == before
    assert "protocol.json" in hashes and "direct_solver.json" in hashes


@pytest.mark.parametrize(
    "field,value", [("status", "running"), ("finished_at", iso(1_800_000_001))]
)
def test_running_or_predeadline_stop_is_not_eligible(tmp_path, field, value):
    study, plan, manifest, ledger = fixture_study(tmp_path)
    manifest[field] = value
    with pytest.raises(ValueError):
        continuation.eligibility(study, plan, manifest, ledger)


@pytest.mark.parametrize(
    "field,value",
    [
        ("study_accounted_micro_usd", 2_500_001),
        ("research_remaining_micro_usd", 499_999),
        ("disabled", True),
    ],
)
def test_financial_or_disabled_provider_cannot_continue(tmp_path, field, value):
    study, plan, manifest, ledger = fixture_study(tmp_path)
    ledger[field] = value
    with pytest.raises(ValueError, match="Budget"):
        continuation.eligibility(study, plan, manifest, ledger)


def test_orphan_existing_directory_never_rerun(tmp_path):
    study, plan, manifest, ledger = fixture_study(tmp_path)
    (study / "episodes" / plan["study_order"][2]["id"]).mkdir()
    with pytest.raises(ValueError, match="partial episode"):
        continuation.eligibility(study, plan, manifest, ledger)


def test_old_budget_stop_or_code_error_forbids_continuation(tmp_path):
    study, plan, manifest, ledger = fixture_study(tmp_path)
    path = study / "episodes" / plan["study_order"][0]["id"] / "result.json"
    row = json.loads(path.read_text())
    row["error"] = "BudgetExceeded"
    save(path, row)
    with pytest.raises(ValueError, match="attributed"):
        continuation.eligibility(study, plan, manifest, ledger)
    row["status"] = "error"
    row["error"] = "KeyError"
    save(path, row)
    with pytest.raises(ValueError, match="Code/worker"):
        continuation.eligibility(study, plan, manifest, ledger)


def journal(path, status, *, accounted=500, reserved=600, error=None):
    records = [
        {
            "type": "request",
            "call": 1,
            "ordinal": 1,
            "retry": 0,
            "reserved_micro_usd": reserved,
            "payload": {
                "model": continuation.MODEL,
                "provider": {"only": ["coreweave/fp4"], "allow_fallbacks": False},
            },
        },
        {
            "type": "response",
            "call": 1,
            "http_status": status,
            "error": error,
            "response": None,
            "accounted_micro_usd": accounted,
        },
    ]
    (path / "events.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in records)
    )


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 405, 413, 415, 422])
def test_fatal_provider_journal_forbids_continuation(tmp_path, status):
    study, plan, manifest, ledger = fixture_study(tmp_path)
    directory = study / "episodes" / plan["study_order"][0]["id"]
    row = json.loads((directory / "result.json").read_text())
    row.update(provider_calls=1, accounted_cost_usd=0.0005)
    save(directory / "result.json", row)
    journal(directory, status)
    with pytest.raises(ValueError, match="Fatal provider"):
        continuation.eligibility(study, plan, manifest, ledger)


def test_accounting_mismatch_and_unsettled_journal_are_rejected(tmp_path):
    study, plan, manifest, ledger = fixture_study(tmp_path)
    directory = study / "episodes" / plan["study_order"][0]["id"]
    row = json.loads((directory / "result.json").read_text())
    row.update(provider_calls=1, accounted_cost_usd=0.0005)
    save(directory / "result.json", row)
    journal(directory, 429, accounted=700, reserved=600)
    with pytest.raises(ValueError, match="reservation"):
        continuation.eligibility(study, plan, manifest, ledger)
    (directory / "events.jsonl").write_text(
        json.dumps({"type": "request", "call": 1}) + "\n"
    )
    with pytest.raises(ValueError, match="Interrupted"):
        continuation.eligibility(study, plan, manifest, ledger)


def test_read_only_ledger_keeps_cumulative_both_waves_cap(tmp_path):
    ledger = tmp_path / "ledger.sqlite3"
    connection = sqlite3.connect(ledger)
    connection.executescript(
        "CREATE TABLE charges(run_id TEXT,bucket TEXT,charged INTEGER,reserved INTEGER,status TEXT);CREATE TABLE settings(name TEXT,value TEXT);"
    )
    connection.executemany(
        "INSERT INTO charges VALUES(?,?,?,?,?)",
        [
            (continuation.STUDY_ID + ":old", "research", 100_000, 100_000, "settled"),
            (continuation.STUDY_ID + ":new", "research", 200_000, 200_000, "reserved"),
            ("other", "research", 500_000, 500_000, "settled"),
        ],
    )
    connection.commit()
    connection.close()
    before = ledger.read_bytes()
    state = continuation.ledger_snapshot(ledger)
    assert state["study_accounted_micro_usd"] == 300_000
    assert state["research_charged_micro_usd"] == 800_000
    assert state["by_run"][continuation.STUDY_ID + ":new"]["pending"] == 1
    assert ledger.read_bytes() == before
    absent = tmp_path / "absent.sqlite3"
    with pytest.raises(ValueError, match="Existing shared"):
        continuation.ledger_snapshot(absent)
    assert not absent.exists()


def test_prepare_preserves_original_manifest_and_no_automatic_execution(
    tmp_path, monkeypatch
):
    study, plan, manifest, ledger = fixture_study(tmp_path)
    original = (study / "manifest.json").read_bytes()
    monkeypatch.setattr(continuation, "load_runtime", lambda *a: object())
    monkeypatch.setattr(continuation, "ledger_snapshot", lambda *a: ledger)
    amendment = continuation.prepare(
        study,
        tmp_path / "runtime.py",
        tmp_path / "ledger",
        continuation.sha(study / "protocol.json"),
    )
    wave = study / continuation.WAVE_NAME
    assert (
        (wave / "wave1-manifest.json").read_bytes()
        == original
        == (study / "manifest.json").read_bytes()
    )
    assert amendment["cumulative_study_cap_usd"] == 3.0
    assert amendment["remaining_cells_in_original_order"] == plan["study_order"][2:]
    assert not (wave / "manifest.json").exists()
    assert len(list((study / "episodes").iterdir())) == 2
    with pytest.raises(FileExistsError):
        continuation.prepare(
            study,
            tmp_path / "runtime.py",
            tmp_path / "ledger",
            continuation.sha(study / "protocol.json"),
        )


def test_changed_prior_evidence_rejected_after_amendment(tmp_path):
    study, plan, manifest, ledger = fixture_study(tmp_path)
    _, _, hashes = continuation.eligibility(study, plan, manifest, ledger)
    (study / "direct_solver.json").write_text("changed")
    with pytest.raises(ValueError, match="prior evidence"):
        continuation.verify_preserved(study, {"preserved_evidence_hashes": hashes})


def test_child_refuses_existing_episode_before_original_executor(tmp_path, monkeypatch):
    row = {"id": "already-exists"}
    (tmp_path / "episodes" / row["id"]).mkdir(parents=True)
    runtime = SimpleNamespace(execute_episode=lambda *a: pytest.fail("must not rerun"))
    monkeypatch.setattr(continuation, "load_runtime", lambda *a: runtime)
    with pytest.raises(FileExistsError, match="never rerun"):
        continuation.execute_frozen_episode(
            "runner", "protocol", "sha", row, {}, str(tmp_path), "ledger", "key", 1
        )


def test_runtime_hash_verification_rejects_changed_or_extra_source(tmp_path):
    root = tmp_path / "runtime"
    script = root / "scripts/run_openrouter_pilot.py"
    script.parent.mkdir(parents=True)
    script.write_text("# fixed\n")
    module = root / "src/cegvr/example.py"
    module.parent.mkdir(parents=True)
    module.write_text("VALUE=1\n")
    plan = {
        "source_commit": continuation.SOURCE_COMMIT,
        "study_id": continuation.STUDY_ID,
        "runtime_hashes": {
            str(p.relative_to(root)): continuation.sha(p) for p in (script, module)
        },
    }
    path = tmp_path / "protocol.json"
    save(path, plan)
    digest = continuation.sha(path)
    assert continuation.verify_runtime_files(script, plan, digest, path) == root
    module.write_text("VALUE=2\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        continuation.verify_runtime_files(script, plan, digest, path)
    module.write_text("VALUE=1\n")
    (module.parent / "unexpected.py").write_text("x=1\n")
    with pytest.raises(ValueError, match="Additional"):
        continuation.verify_runtime_files(script, plan, digest, path)


def test_mocked_continuation_records_only_missing_cells_and_preserves_wave1(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(continuation.time, "time", lambda: 1_800_003_000)
    monkeypatch.setattr(continuation, "utc_now", lambda: iso(1_800_003_000))
    study, plan, manifest, ledger = fixture_study(tmp_path, observed=748)
    original_manifest = (study / "manifest.json").read_bytes()
    original_result = study / "episodes" / plan["study_order"][0]["id"] / "result.json"
    original_result_bytes = original_result.read_bytes()
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        "".join(json.dumps(row) + "\n" for row in plan["selected_tasks"])
    )
    executed = []

    def original_executor(
        row, problem, output, ledger_path, key_file, deadline, allowance
    ):
        assert allowance == 3.0 and row in plan["study_order"][748:]
        assert row["seed"] in (17, 29, 43)
        location = Path(output) / "episodes" / row["id"]
        location.mkdir(exist_ok=False)
        result = {
            **row,
            "status": "complete",
            "error": None,
            "outcome": None,
            "provider_calls": 0,
            "accounted_cost_usd": 0.0,
        }
        save(location / "result.json", result)
        executed.append(row["id"])
        return result

    runtime = SimpleNamespace(
        DATASET=dataset,
        execute_episode=original_executor,
        reconcile_worker_error=lambda *a: pytest.fail("unexpected mock worker error"),
    )
    monkeypatch.setattr(continuation, "load_runtime", lambda *a: runtime)
    monkeypatch.setattr(continuation, "ledger_snapshot", lambda *a: ledger)

    class FakeStore:
        CAPS = {"research": 12_000_000, "public": 8_000_000}
        TOTAL_CAP = 20_000_000

        def __init__(self, path):
            pass

        def budget(self, bucket):
            return {"charged_usd": 1.0, "remaining_usd": 11.0, "disabled": False}

    package, store_module = ModuleType("forgerl"), ModuleType("forgerl.store")
    store_module.Store = FakeStore
    monkeypatch.setitem(sys.modules, "forgerl", package)
    monkeypatch.setitem(sys.modules, "forgerl.store", store_module)

    class ImmediatePool:
        def __init__(self, **kwargs):
            assert kwargs["max_workers"] == 8

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def submit(self, function, *args):
            future = Future()
            try:
                future.set_result(function(*args))
            except BaseException as error:
                future.set_exception(error)
            return future

    monkeypatch.setattr(continuation, "ProcessPoolExecutor", ImmediatePool)
    key = tmp_path / "private-key"
    key.write_text("fixture-only-no-network")
    frozen_sha = continuation.sha(study / "protocol.json")
    continuation.prepare(study, "frozen_runtime", "original_ledger", frozen_sha)
    wave = study / continuation.WAVE_NAME
    amendment_sha = continuation.sha(wave / "amendment.json")
    publication = (
        "https://github.com/stelioszach03/llm-smt-verifiable-reasoning/commit/"
        + "a" * 40
    )
    result = continuation.run(
        study,
        "frozen_runtime",
        "original_ledger",
        key,
        frozen_sha,
        amendment_sha,
        publication,
    )
    assert executed == [r["id"] for r in plan["study_order"][748:]]
    assert result["completed"] == 750 and result["missing"] == []
    assert result["recorded_status_counts"] == {"stopped": 1, "complete": 749}
    assert result["status"] == "complete"  # coverage, not successful certificates
    assert result["elapsed_seconds"] == 3000
    assert result["continuation_elapsed_seconds"] == 0
    assert original_result.read_bytes() == original_result_bytes
    assert (wave / "wave1-manifest.json").read_bytes() == original_manifest
    assert read_json(wave / "manifest.json")["new_recorded_cells"] == 2
    with pytest.raises(ValueError, match="already started"):
        continuation.run(
            study,
            "frozen_runtime",
            "original_ledger",
            key,
            frozen_sha,
            amendment_sha,
            publication,
        )


def read_json(path):
    return json.loads(path.read_text())
