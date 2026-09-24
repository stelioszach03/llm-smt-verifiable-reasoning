#!/usr/bin/env python3
"""Operator-only, single bounded continuation of unlaunched pilot cells.

This helper is outside the frozen evaluation runtime. It never changes that
runtime, the original protocol, prior episode files or the cumulative study cap.
Prepare an amendment, publish it, then explicitly execute against its hash.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import math
import multiprocessing
from pathlib import Path
import re
import sqlite3
import sys
import time
from urllib.parse import quote


SOURCE_COMMIT = "dc7b9de89f3a507705b259c870af82eda763621f"
STUDY_ID = "cegvr-openrouter-pilot1-20260924"
MODEL = "openai/gpt-oss-20b"
WINDOW_SECONDS = 2700
STUDY_CAP = 3_000_000
# The original Store rejects a reservation exceeding $0.50. Requiring at least
# this headroom rules out an ambiguous financial stop when the old result only
# records StudyStopped, without retaining its exact reason.
SAFE_HEADROOM = 500_000
WAVE_NAME = "continuation-wave2"
FATAL_HTTP = {400, 401, 402, 403, 404, 405, 413, 415, 422}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Evidence timestamps must include a timezone")
    return parsed.timestamp()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def atomic_write(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".continuation.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    temporary.replace(path)


def verify_runtime_files(
    runtime_script, protocol, expected_protocol_sha, protocol_path
):
    runtime_script = Path(runtime_script).resolve()
    root = runtime_script.parent.parent
    if (
        runtime_script.name != "run_openrouter_pilot.py"
        or runtime_script.parent.name != "scripts"
    ):
        raise ValueError("Supply the explicit original frozen runner path")
    if sha(protocol_path) != expected_protocol_sha:
        raise ValueError("Original protocol hash mismatch")
    if (
        protocol.get("source_commit") != SOURCE_COMMIT
        or protocol.get("study_id") != STUDY_ID
    ):
        raise ValueError("Continuation supports only the original frozen pilot")
    for relative, expected in protocol["runtime_hashes"].items():
        item = Path(relative)
        target = root / item
        if (
            item.is_absolute()
            or ".." in item.parts
            or target.is_symlink()
            or root not in target.resolve().parents
        ):
            raise ValueError("Unsafe runtime manifest entry")
        if not target.is_file() or sha(target) != expected:
            raise ValueError(f"Frozen runtime hash mismatch: {relative}")
    if protocol["runtime_hashes"].get("scripts/run_openrouter_pilot.py") != sha(
        runtime_script
    ):
        raise ValueError("Runner is not the captured frozen runtime")
    expected_src = {
        name
        for name in protocol["runtime_hashes"]
        if name.startswith("src/") and name.endswith(".py")
    }
    actual_src = {str(p.relative_to(root)) for p in (root / "src").rglob("*.py")}
    if expected_src != actual_src:
        raise ValueError("Additional or missing source files in frozen runtime")
    return root


def load_runtime(runtime_script, protocol_path, expected_protocol_sha):
    protocol = read_json(protocol_path)
    root = verify_runtime_files(
        runtime_script, protocol, expected_protocol_sha, protocol_path
    )
    for name, module in list(sys.modules.items()):
        if name == "cegvr" or name.startswith("cegvr."):
            source = getattr(module, "__file__", None)
            if source and root / "src" not in Path(source).resolve().parents:
                raise ValueError("A different CEGVR runtime is already imported")
    sys.path.insert(0, str(root / "src"))
    spec = importlib.util.spec_from_file_location(
        "cegvr_frozen_wave_runtime", runtime_script
    )
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    if (
        runtime.runtime_hashes() != protocol["runtime_hashes"]
        or runtime.STUDY_ID != STUDY_ID
    ):
        raise ValueError("Imported runtime differs from the original freeze")
    return runtime


def ledger_snapshot(ledger, study_id=STUDY_ID):
    ledger = Path(ledger).resolve()
    if not ledger.is_file():
        raise ValueError("Existing shared ledger required; no replacement is created")
    connection = sqlite3.connect("file:" + quote(str(ledger)) + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        all_charges = connection.execute(
            "SELECT bucket,charged FROM charges"
        ).fetchall()
        rows = connection.execute(
            "SELECT run_id,charged,reserved,status FROM charges WHERE substr(run_id,1,?)=?",
            (len(study_id) + 1, study_id + ":"),
        ).fetchall()
        disabled = bool(
            connection.execute(
                "SELECT 1 FROM settings WHERE name='provider_disabled'"
            ).fetchone()
        )
    finally:
        connection.close()
    by_run = {}
    for row in rows:
        item = by_run.setdefault(
            row["run_id"], {"charged": 0, "reservations": 0, "pending": 0}
        )
        item["charged"] += row["charged"]
        item["reservations"] += 1
        item["pending"] += row["status"] == "reserved"
    research = sum(row["charged"] for row in all_charges if row["bucket"] == "research")
    total = sum(row["charged"] for row in all_charges)
    stat = ledger.stat()
    return {
        "study_accounted_micro_usd": sum(row["charged"] for row in rows),
        "research_charged_micro_usd": research,
        "research_remaining_micro_usd": max(
            0, min(12_000_000 - research, 20_000_000 - total)
        ),
        "disabled": disabled,
        "by_run": by_run,
        "ledger_identity_sha256": hashlib.sha256(
            f"{ledger}|{stat.st_dev}|{stat.st_ino}".encode()
        ).hexdigest(),
    }


def validate_protocol(protocol):
    expected = {
        "source_commit": SOURCE_COMMIT,
        "study_id": STUDY_ID,
        "model": MODEL,
        "temperature": 0.2,
        "max_output_tokens": 2048,
        "max_rounds": 4,
        "per_round_candidates": 4,
        "solver_timeout_ms": 1500,
        "witness_policy": "withhold",
        "allowance_usd": 3.0,
        "workers": 8,
        "operational_seconds": WINDOW_SECONDS,
        "seeds": [17, 29, 43],
    }
    if any(protocol.get(k) != value for k, value in expected.items()):
        raise ValueError(
            "Original frozen settings differ from this bounded continuation"
        )
    routing = protocol.get("provider", {})
    if (
        routing.get("only") != ["coreweave/fp4"]
        or routing.get("quantizations") != ["fp4"]
        or routing.get("allow_fallbacks") is not False
    ):
        raise ValueError("Provider pin or fallback policy differs")
    rows = protocol["study_order"]
    if len(rows) != 750 or len({r["id"] for r in rows}) != 750:
        raise ValueError("Expected the original 750 distinct cells")
    for row in rows:
        computed = hashlib.sha256(
            f"{row['problem_id']}|{row['seed']}|{row['arm']}".encode()
        ).hexdigest()[:20]
        if not re.fullmatch(r"[a-f0-9]{20}", row["id"]) or row["id"] != computed:
            raise ValueError("Unexpected episode identity")


def inspect_episode(path, expected, original_deadline):
    row = read_json(path / "result.json")
    if any(row.get(k) != v for k, v in expected.items()):
        raise ValueError("Existing episode identity differs from frozen cell")
    if row.get("status") not in ("complete", "stopped") or row.get(
        "accounting_recovery"
    ):
        raise ValueError("Code/worker/accounting errors prevent automatic continuation")
    if row["status"] == "complete" and row.get("error") is not None:
        raise ValueError("Completed episode carries an unexpected error")
    if row["status"] == "stopped":
        if (
            row.get("error") != "StudyStopped"
            or timestamp(row["finished_at"]) < original_deadline
        ):
            raise ValueError(
                "An observed stop cannot be attributed to the admission deadline"
            )
    events_path = path / "events.jsonl"
    events = (
        [json.loads(line) for line in events_path.read_text().splitlines()]
        if events_path.exists()
        else []
    )
    requests, responses = {}, {}
    for event in events:
        if event.get("type") not in ("request", "response"):
            raise ValueError("Unexpected transport journal event")
        target = requests if event["type"] == "request" else responses
        if event["call"] in target:
            raise ValueError("Duplicate journal request/response")
        target[event["call"]] = event
    if set(requests) != set(responses) or len(requests) != row["provider_calls"]:
        raise ValueError("Interrupted or unreconciled provider journal")
    charged = 0
    for call, response in responses.items():
        request = requests[call]
        payload = request["payload"]
        if (
            payload.get("model") != MODEL
            or payload.get("provider", {}).get("only") != ["coreweave/fp4"]
            or payload.get("provider", {}).get("allow_fallbacks") is not False
        ):
            raise ValueError("Journal contains different provider settings")
        if response.get("http_status") in FATAL_HTTP or response.get("error") in (
            "provider_identity_mismatch",
            "provider_error_in_response",
        ):
            raise ValueError("Fatal provider/request/access event forbids continuation")
        cost, reserve = response["accounted_micro_usd"], request["reserved_micro_usd"]
        if (
            type(cost) is not int
            or type(reserve) is not int
            or not 0 <= cost <= reserve <= SAFE_HEADROOM
        ):
            raise ValueError("Unreconciled or exceeded cost reservation")
        visible = response.get("response")
        if visible is not None and (
            visible.get("model") != MODEL or visible.get("provider") != "CoreWeave"
        ):
            raise ValueError("Returned provider identity mismatch")
        charged += cost
    if not math.isclose(row["accounted_cost_usd"], charged / 1e6, abs_tol=1e-9):
        raise ValueError("Episode accounting differs from its transport journal")
    return row, charged, len(requests)


def eligibility(study, protocol, manifest, ledger_state):
    validate_protocol(protocol)
    if manifest.get("status") != "incomplete" or not manifest.get("finished_at"):
        raise ValueError("Original study must be finished and incomplete")
    started = timestamp(manifest["started_at"])
    deadline = started + WINDOW_SECONDS
    if timestamp(manifest["finished_at"]) < deadline:
        raise ValueError("Original wave did not reach its frozen admission deadline")
    if manifest["protocol_sha256"] != sha(study / "protocol.json"):
        raise ValueError("Manifest does not match the frozen protocol")
    if (
        ledger_state["disabled"]
        or STUDY_CAP - ledger_state["study_accounted_micro_usd"] < SAFE_HEADROOM
        or ledger_state["research_remaining_micro_usd"] < SAFE_HEADROOM
    ):
        raise ValueError("Budget headroom insufficient to rule out a financial stop")
    expected = {r["id"]: r for r in protocol["study_order"]}
    records, hashes = {}, {}
    episodes = study / "episodes"
    for directory in sorted(episodes.iterdir()):
        if (
            directory.is_symlink()
            or not directory.is_dir()
            or directory.name not in expected
        ):
            raise ValueError("Unexpected existing episode path")
        if not (directory / "result.json").is_file():
            raise ValueError(
                "Existing partial episode cannot be rerun or silently skipped"
            )
        row, charged, calls = inspect_episode(
            directory, expected[directory.name], deadline
        )
        ledger_row = ledger_state["by_run"].get(
            STUDY_ID + ":" + row["id"], {"charged": 0, "reservations": 0, "pending": 0}
        )
        if ledger_row != {"charged": charged, "reservations": calls, "pending": 0}:
            raise ValueError("Episode journal and original ledger do not reconcile")
        records[row["id"]] = row
        for path in directory.rglob("*"):
            if path.is_symlink():
                raise ValueError("Symlink in original evidence")
            if path.is_file():
                hashes[str(path.relative_to(study))] = sha(path)
    missing = [r for r in protocol["study_order"] if r["id"] not in records]
    if (
        not missing
        or manifest["completed"] != len(records)
        or manifest["planned"] != 750
        or manifest.get("missing") != missing
    ):
        raise ValueError("Original completed/missing matrix does not reconcile")
    if set(ledger_state["by_run"]) - {STUDY_ID + ":" + key for key in records}:
        raise ValueError(
            "Prior study reservations exist outside preserved result records"
        )
    hashes["protocol.json"] = sha(study / "protocol.json")
    hashes["direct_solver.json"] = sha(study / "direct_solver.json")
    return records, missing, hashes


def prepare(study, runtime_script, ledger, expected_protocol_sha):
    study = Path(study).resolve()
    protocol = read_json(study / "protocol.json")
    load_runtime(runtime_script, study / "protocol.json", expected_protocol_sha)
    manifest = read_json(study / "manifest.json")
    state = ledger_snapshot(ledger)
    records, missing, hashes = eligibility(study, protocol, manifest, state)
    wave = study / WAVE_NAME
    wave.mkdir(exist_ok=False)
    with (wave / "wave1-manifest.json").open("xb") as stream:
        stream.write((study / "manifest.json").read_bytes())
    amendment = {
        "kind": "operational_admission_extension_not_unchanged_preregistration",
        "prepared_at": utc_now(),
        "study_id": STUDY_ID,
        "original_protocol_sha256": expected_protocol_sha,
        "original_source_commit": SOURCE_COMMIT,
        "original_manifest_sha256": sha(wave / "wave1-manifest.json"),
        "preserved_evidence_hashes": hashes,
        "helper_source_sha256": sha(Path(__file__)),
        "ledger_identity_sha256": state["ledger_identity_sha256"],
        "already_recorded_cells": len(records),
        "remaining_cell_count": len(missing),
        "remaining_cells_in_original_order": missing,
        "additional_admission_seconds": WINDOW_SECONDS,
        "workers": protocol["workers"],
        "cumulative_study_cap_usd": 3.0,
        "study_accounted_usd_at_prepare": state["study_accounted_micro_usd"] / 1e6,
        "preserved_status_counts": dict(Counter(r["status"] for r in records.values())),
        "scope": "Only previously unlaunched cells. Existing complete, stopped and failed outcomes are never rerun, overwritten or reclassified. No change to source, model/provider, seeds, selection, original remaining order, witness policy, candidate/solver caps or original shared ledger.",
        "completion_definition": "750 recorded cells means matrix coverage, not 750 successful certificates. Deadline-stopped original episodes remain observed unsuccessful executions, not model-quality-only failures.",
        "publication_requirement": "Operator must publish this exact JSON and its explanation before execution and supply the public commit reference plus SHA256. This helper does not attest remote publication itself.",
        "window_definition": "One additional 45-minute request-admission window; in-flight work drains under the original request limits. This is an explicit post-freeze operational amendment, not the originally unchanged stopping protocol.",
    }
    write_new(wave / "amendment.json", amendment)
    explanation = (
        "# CEGVR pilot: operational admission-window amendment\n\n"
        f"Prepared at {amendment['prepared_at']}, after the first frozen 45-minute admission window completed. "
        f"The original wave recorded {len(records)}/750 cells; {len(missing)} were never launched.\n\n"
        "One additional 45-minute admission window is authorized for those unlaunched cells only, in their original frozen order. "
        "The original model/provider, seeds, code, task selection, candidate/solver budgets and cumulative $3 study cap are unchanged. "
        "The same original shared ledger and study ID count both waves. This is a publicly disclosed operational amendment, not a claim that the original stopping protocol stayed unchanged.\n\n"
        "Every prior result and transport record is preserved byte-for-byte. Original deadline-stopped episodes remain unsuccessful observed executions; they are not retried or attributed solely to model quality. "
        "750 recorded cells will denote coverage, not 750 successes. No third wave is enabled by this helper.\n\n"
        f"Original protocol SHA256: `{expected_protocol_sha}`. Source commit: `{SOURCE_COMMIT}`. "
        f"Exact amendment JSON SHA256: `{sha(wave / 'amendment.json')}`.\n"
    )
    (wave / "AMENDMENT.md").write_text(explanation)
    return amendment


def verify_preserved(study, amendment):
    for relative, expected in amendment["preserved_evidence_hashes"].items():
        if sha(study / relative) != expected:
            raise ValueError("A prior evidence file changed; continuation forbidden")


def execute_frozen_episode(
    runtime_script,
    protocol_path,
    expected_protocol_sha,
    row,
    problem,
    output,
    ledger,
    key_file,
    deadline,
):
    runtime = load_runtime(runtime_script, protocol_path, expected_protocol_sha)
    if (Path(output) / "episodes" / row["id"]).exists():
        raise FileExistsError("Episode already exists; never rerun it")
    return runtime.execute_episode(
        row, problem, output, ledger, key_file, deadline, 3.0
    )


def run(
    study,
    runtime_script,
    ledger,
    key_file,
    expected_protocol_sha,
    expected_amendment_sha,
    publication_url,
):
    study = Path(study).resolve()
    if not re.fullmatch(
        r"https://github\.com/stelioszach03/llm-smt-verifiable-reasoning/commit/[a-f0-9]{40}",
        publication_url or "",
    ):
        raise ValueError("An explicit public amendment commit reference is required")
    if not Path(key_file).is_file():
        raise ValueError("Credential file is unavailable")
    wave = study / WAVE_NAME
    with (wave / "execution.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (wave / "manifest.json").exists():
            raise ValueError(
                "Continuation already started; no second execution or third wave"
            )
        if sha(wave / "amendment.json") != expected_amendment_sha:
            raise ValueError("Amendment differs from the published hash")
        amendment = read_json(wave / "amendment.json")
        if (
            amendment["helper_source_sha256"] != sha(Path(__file__))
            or amendment["original_protocol_sha256"] != expected_protocol_sha
        ):
            raise ValueError("Helper or original protocol changed after amendment")
        if (
            sha(study / "manifest.json") != amendment["original_manifest_sha256"]
            or sha(wave / "wave1-manifest.json")
            != amendment["original_manifest_sha256"]
        ):
            raise ValueError("Original wave manifest changed after amendment")
        verify_preserved(study, amendment)
        runtime = load_runtime(
            runtime_script, study / "protocol.json", expected_protocol_sha
        )
        protocol = read_json(study / "protocol.json")
        state = ledger_snapshot(ledger)
        if state["ledger_identity_sha256"] != amendment["ledger_identity_sha256"]:
            raise ValueError("Continuation must use the same original ledger file")
        original_manifest = read_json(wave / "wave1-manifest.json")
        old_records, missing, hashes = eligibility(
            study, protocol, original_manifest, state
        )
        if (
            missing != amendment["remaining_cells_in_original_order"]
            or hashes != amendment["preserved_evidence_hashes"]
        ):
            raise ValueError(
                "Remaining cells or evidence changed after public amendment"
            )
        # Imports the exact shared Store used by the frozen runtime, with its
        # original global/research caps. No budget is reset or enlarged.
        from forgerl.store import Store

        if (
            Store.CAPS != {"research": 12_000_000, "public": 8_000_000}
            or Store.TOTAL_CAP != 20_000_000
        ):
            raise ValueError("Original shared-ledger caps changed")
        store = Store(ledger)
        problems = {
            p["problem_id"]: p
            for p in map(json.loads, runtime.DATASET.read_text().splitlines())
        }
        started = time.time()
        deadline = started + WINDOW_SECONDS
        wave_manifest = {
            "status": "running",
            "started_at": utc_now(),
            "planned_new_cells": len(missing),
            "new_recorded_cells": 0,
            "amendment_sha256": expected_amendment_sha,
            "published_amendment_reference": publication_url,
            "publication_verification": "Operator-supplied public reference; reviewed before invocation, not fetched by this helper",
            "original_manifest_sha256": amendment["original_manifest_sha256"],
        }
        write_new(wave / "manifest.json", wave_manifest)
        rows, new_records, stopped = iter(missing), {}, False
        context = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=8, mp_context=context) as executor:
            pending = {}
            while True:
                while not stopped and time.time() < deadline and len(pending) < 8:
                    row = next(rows, None)
                    if row is None:
                        break
                    if (study / "episodes" / row["id"]).exists():
                        raise FileExistsError(
                            "A previously unlaunched episode now exists"
                        )
                    future = executor.submit(
                        execute_frozen_episode,
                        str(Path(runtime_script).resolve()),
                        str(study / "protocol.json"),
                        expected_protocol_sha,
                        row,
                        problems[row["problem_id"]],
                        str(study),
                        str(Path(ledger).resolve()),
                        str(Path(key_file).resolve()),
                        deadline,
                    )
                    pending[future] = row
                if not pending:
                    break
                ready, _ = wait(pending, timeout=10, return_when=FIRST_COMPLETED)
                for future in ready:
                    row = pending.pop(future)
                    try:
                        result = future.result()
                    except Exception as exc:
                        result_path = study / "episodes" / row["id"] / "result.json"
                        # Never overwrite a result already written by a worker.
                        result = (
                            read_json(result_path)
                            if result_path.exists()
                            else runtime.reconcile_worker_error(
                                row, study, store, type(exc).__name__
                            )
                        )
                        stopped = True
                    new_records[row["id"]] = result
                    if result["status"] != "complete":
                        stopped = True
                wave_manifest.update(
                    new_recorded_cells=len(new_records),
                    elapsed_seconds=time.time() - started,
                )
                atomic_write(wave / "manifest.json", wave_manifest)
        verify_preserved(study, amendment)
        combined = {**old_records, **new_records}
        remaining = [
            row for row in protocol["study_order"] if row["id"] not in combined
        ]
        final_budget = ledger_snapshot(ledger)
        if final_budget["study_accounted_micro_usd"] > STUDY_CAP:
            raise RuntimeError("Cumulative study accounting exceeded original cap")
        wave_manifest.update(
            status="complete" if not remaining else "incomplete",
            finished_at=utc_now(),
            elapsed_seconds=time.time() - started,
            new_recorded_cells=len(new_records),
            new_status_counts=dict(Counter(r["status"] for r in new_records.values())),
            remaining_unlaunched=remaining,
            cumulative_study_accounted_cost_usd=final_budget[
                "study_accounted_micro_usd"
            ]
            / 1e6,
        )
        atomic_write(wave / "manifest.json", wave_manifest)
        final = {
            **original_manifest,
            "status": "complete" if not remaining else "incomplete",
            "completed": len(combined),
            "missing": remaining,
            "finished_at": utc_now(),
            "elapsed_seconds": time.time() - timestamp(original_manifest["started_at"]),
            "elapsed_seconds_definition": "Total wall time since the original wave started, including the publication/continuation pause; individual wave times are retained separately.",
            "continuation_elapsed_seconds": wave_manifest["elapsed_seconds"],
            "budget_after": store.budget("research"),
            "accounted_cost_delta_usd": final_budget["research_charged_micro_usd"] / 1e6
            - original_manifest["budget_before"]["charged_usd"],
            "cumulative_study_accounted_cost_usd": final_budget[
                "study_accounted_micro_usd"
            ]
            / 1e6,
            "operational_amendment_sha256": expected_amendment_sha,
            "published_amendment_reference": publication_url,
            "original_wave_manifest": WAVE_NAME + "/wave1-manifest.json",
            "continuation_manifest": WAVE_NAME + "/manifest.json",
            "recorded_status_counts": dict(
                Counter(r["status"] for r in combined.values())
            ),
            "completion_definition": amendment["completion_definition"],
            "original_admission_seconds": WINDOW_SECONDS,
            "additional_admission_seconds": WINDOW_SECONDS,
        }
        atomic_write(study / "manifest.json", final)
        return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run"))
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--runtime-script", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--expected-protocol-sha256", required=True)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--expected-amendment-sha256")
    parser.add_argument("--published-amendment-url")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(
            args.study, args.runtime_script, args.ledger, args.expected_protocol_sha256
        )
        print(
            json.dumps(
                {
                    "prepared": True,
                    "remaining": result["remaining_cell_count"],
                    "amendment_sha256": sha(args.study / WAVE_NAME / "amendment.json"),
                },
                indent=2,
            )
        )
    else:
        if (
            not args.key_file
            or not args.expected_amendment_sha256
            or not args.published_amendment_url
        ):
            parser.error(
                "run requires credential path, published amendment hash and public commit reference"
            )
        result = run(
            args.study,
            args.runtime_script,
            args.ledger,
            args.key_file,
            args.expected_protocol_sha256,
            args.expected_amendment_sha256,
            args.published_amendment_url,
        )
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "recorded_cells": result["completed"],
                    "planned_cells": result["planned"],
                    "missing_cells": len(result["missing"]),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
