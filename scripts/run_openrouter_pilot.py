"""Freeze and execute a finite prospective candidate-verification pilot.

The paid operator command needs the existing Forge Store on PYTHONPATH. It never
starts a model server or exposes an inference endpoint. No output is overwritten.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing
from pathlib import Path
import random
import subprocess
import time

from cegvr.candidate.repair import repair_candidates_until_certified
from cegvr.candidate.types import CandidateOutput, ExperimentArm
from cegvr.candidate.verifier import verify_linear_candidate
from cegvr.generation.openrouter_study import AccountedOpenRouter, MODEL, ROUTING

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data/linear/problems.jsonl"
STUDY_ID = "cegvr-openrouter-pilot1-20260924"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def runtime_hashes():
    paths = sorted((ROOT / "src").rglob("*.py"))
    paths += [Path(__file__).resolve(), DATASET, ROOT / "requirements-study.txt"]
    return {str(p.relative_to(ROOT)): digest(p) for p in paths}


def select_tasks(problems):
    chosen = []
    for label, count in (("sat", 30), ("unsat", 20)):
        eligible = [p for p in problems if p["ground_truth"].lower() == label]
        eligible.sort(
            key=lambda p: hashlib.sha256(
                ("cegvr-pilot-v1|" + p["problem_id"]).encode()
            ).hexdigest()
        )
        chosen.extend(eligible[:count])
    if len(chosen) != 50:
        raise ValueError("Dataset cannot supply the frozen strata")
    return chosen


def freeze(output):
    output.mkdir(parents=True, exist_ok=False)
    problems = [json.loads(line) for line in DATASET.read_text().splitlines()]
    chosen = select_tasks(problems)
    rows = []
    for task in chosen:
        for seed in (17, 29, 43):
            for arm in ExperimentArm:
                ident = hashlib.sha256(
                    f"{task['problem_id']}|{seed}|{arm.value}".encode()
                ).hexdigest()[:20]
                rows.append(
                    {
                        "id": ident,
                        "problem_id": task["problem_id"],
                        "ground_truth": task["ground_truth"].lower(),
                        "seed": seed,
                        "arm": arm.value,
                    }
                )
    random.Random(20260924).shuffle(rows)
    protocol = {
        "study_id": STUDY_ID,
        "frozen_at": utc_now(),
        "dataset_sha256": digest(DATASET),
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "runtime_hashes": runtime_hashes(),
        "model": MODEL,
        "provider": ROUTING,
        "temperature": 0.2,
        "max_output_tokens": 2048,
        "reasoning_effort": "low",
        "seeds": [17, 29, 43],
        "arms": [a.value for a in ExperimentArm],
        "max_rounds": 4,
        "per_round_candidates": 4,
        "solver_timeout_ms": 1500,
        "witness_policy": "withhold",
        "allowance_usd": 3.0,
        "workers": 8,
        "operational_seconds": 2700,
        "retry_policy": "Only HTTP429: at most2 transport retries, waits2s/4s, same payload; all charged/accounted.",
        "selection": "SHA256('cegvr-pilot-v1|'+problem_id), smallest30SAT/20UNSAT; existingpublic500taskdataset, not unseen/external.",
        "selected_tasks": [
            {"problem_id": p["problem_id"], "ground_truth": p["ground_truth"].lower()}
            for p in chosen
        ],
        "study_order": rows,
        "primary_endpoint": "SAT assignment certification among30tasks x3requestedseeds perarm",
        "secondary_endpoints": [
            "UNSAT claim certification by Z3",
            "overall certification",
            "all provider calls/cost/tokens",
            "repair after first failure",
        ],
        "analysis": "Descriptive paired task/seed comparisons; missingunlaunched not failures; no significance or generalreasoning claim.",
        "accounting": "Every HTTPattempt reserved in unchanged existingForge researchledger; unknowncost retainsfullreservation; separate$3study cap; providerusagecost excludescreditfees.",
        "known_limits": [
            "Syntheticpubliclinearfeasibility",
            "simplecontradictoryUNSATinstances",
            "directZ3can solve theseproblems withoutLLM",
            "requestedseed doesn'tguaranteedeterminism",
            "hostedcheckpointversionnotpinnable",
            "equalcandidatecapsarenotequalcost",
        ],
    }
    write(output / "protocol.json", protocol)
    print(
        json.dumps(
            {
                "frozen": str(output / "protocol.json"),
                "sha256": digest(output / "protocol.json"),
                "planned": len(rows),
            }
        )
    )


def solver_control(output):
    """Measure direct oracle and always-UNSAT/copy-witness control; zero inference."""
    rows = []
    for problem in map(json.loads, DATASET.read_text().splitlines()):
        start = time.perf_counter()
        verification = verify_linear_candidate(
            problem, CandidateOutput(status="unsat"), timeout_ms=1500
        )
        first = verification.model_dump(mode="json")
        copied = None
        if verification.sat_witness:
            copied = verify_linear_candidate(
                problem,
                CandidateOutput(status="sat", assignment=verification.sat_witness),
                timeout_ms=1500,
            )
        rows.append(
            {
                "problem_id": problem["problem_id"],
                "ground_truth": problem["ground_truth"],
                "direct_status": verification.verifier_result,
                "direct_solver_ms": verification.solver_time_ms,
                "first_claim_certified": verification.verified_outcome
                == "CERTIFIED_UNSAT",
                "oracle_control_certified": verification.verified_outcome
                == "CERTIFIED_UNSAT"
                or (copied is not None and copied.verified_outcome == "CERTIFIED_SAT"),
                "oracle_control_calls": 2 if copied is not None else 1,
                "wall_ms": (time.perf_counter() - start) * 1000,
                "first_outcome": first["verified_outcome"],
            }
        )
    write(
        output / "direct_solver.json",
        {
            "measured_at": utc_now(),
            "dataset_sha256": digest(DATASET),
            "provider_calls": 0,
            "rows": rows,
        },
    )
    if any(
        row["direct_status"] != row["ground_truth"].lower()
        or not row["oracle_control_certified"]
        for row in rows
    ):
        raise ValueError(
            "Direct solver preflight disagrees with dataset or cannot certify a control"
        )


def execute_episode(row, problem, output, ledger, key_file, deadline, allowance):
    from forgerl.store import Store

    location = Path(output) / "episodes" / row["id"]
    location.mkdir(parents=True, exist_ok=False)
    generator = AccountedOpenRouter(
        key=Path(key_file).read_text().strip(),
        store=Store(ledger),
        study_id=STUDY_ID,
        run_id=STUDY_ID + ":" + row["id"],
        repeat=row["seed"],
        events_path=location / "events.jsonl",
        lock_path=Path(output) / "budget.lock",
        deadline=deadline,
        allowance_usd=allowance,
    )
    result = {
        **row,
        "started_at": utc_now(),
        "status": "complete",
        "error": None,
        "outcome": None,
    }
    start = time.perf_counter()
    try:
        result["outcome"] = repair_candidates_until_certified(
            problem,
            generator,
            arm=ExperimentArm(row["arm"]),
            max_rounds=4,
            per_round_budget=4,
            timeout_ms=1500,
            witness_policy="withhold",
        )
    except Exception as exc:
        # Never publish arbitrary upstream error strings or credentials.
        result.update(
            status="stopped"
            if type(exc).__name__ in ("StudyStopped", "BudgetExceeded")
            else "error",
            error=type(exc).__name__,
        )
    result.update(
        finished_at=utc_now(),
        wall_latency_ms=(time.perf_counter() - start) * 1000,
        provider_calls=generator.calls,
        accounted_cost_usd=generator.accounted_micro_usd / 1e6,
        provider_reported_cost_usd=generator.provider_reported_cost_usd
        if generator.known_cost_calls
        else None,
        known_cost_calls=generator.known_cost_calls,
        uncertain_calls=generator.uncertain_calls,
        transport_errors=generator.transport_errors,
    )
    write(location / "result.json", result)
    return result


def reconcile_worker_error(row, output, store, error_type):
    """Recover known usage from durable evidence after a worker-level exception."""
    location = output / "episodes" / row["id"]
    location.mkdir(parents=True, exist_ok=True)
    events = []
    if (location / "events.jsonl").exists():
        for line in (location / "events.jsonl").read_text().splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                continue  # Preserve the interrupted last line in original evidence.
    with store.connect() as connection:
        charges = connection.execute(
            "SELECT charged,status,usage_json FROM charges WHERE run_id=?",
            (STUDY_ID + ":" + row["id"],),
        ).fetchall()
    known = []
    for charge in charges:
        usage = json.loads(charge["usage_json"] or "{}") or {}
        if usage.get("cost") is not None:
            known.append(usage["cost"])
    result = {
        **row,
        "status": "error",
        "error": error_type,
        "outcome": None,
        "provider_calls": sum(e.get("type") == "request" for e in events),
        "accounted_cost_usd": sum(c["charged"] for c in charges) / 1e6,
        "provider_reported_cost_usd": sum(known) if known else None,
        "uncertain_calls": sum(
            c["status"] in ("reserved", "uncertain") for c in charges
        ),
        "transport_errors": sum(
            e.get("type") == "response" and e.get("error") is not None for e in events
        ),
        "wall_latency_ms": None,
        "accounting_recovery": "Ledger charges and complete journal records; absent wall latency is unknown. Reserved-but-unlogged calls remain charged, not assumed sent.",
        "ledger_reservations": len(charges),
    }
    write(location / "result.json", result)
    return result


def run(output, ledger, key_file, expected_protocol_sha256):
    if not Path(ledger).is_file():
        raise ValueError(
            "The existing shared ledger must exist; never create a replacement"
        )
    if digest(output / "protocol.json") != expected_protocol_sha256:
        raise ValueError("Protocol differs from externally recorded freeze hash")
    protocol = json.loads((output / "protocol.json").read_text())
    if protocol["runtime_hashes"] != runtime_hashes():
        raise ValueError("Runtime changed after freeze")
    if (output / "manifest.json").exists():
        raise ValueError("Study already started; cannot replace or selectively rerun")
    from forgerl.store import Store

    store = Store(ledger)
    initial_budget = store.budget("research")
    if (
        initial_budget["disabled"]
        or initial_budget["remaining_usd"] < protocol["allowance_usd"]
    ):
        raise ValueError("Shared budget insufficient or disabled")
    problems = {
        p["problem_id"]: p for p in map(json.loads, DATASET.read_text().splitlines())
    }
    started = time.time()
    deadline = started + protocol["operational_seconds"]
    rows = iter(protocol["study_order"])
    results = []
    manifest = {
        "status": "running",
        "started_at": utc_now(),
        "protocol_sha256": digest(output / "protocol.json"),
        "planned": len(protocol["study_order"]),
        "completed": 0,
        "budget_before": initial_budget,
    }
    write(output / "manifest.json", manifest)
    solver_control(output)
    stopped = False
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(
        max_workers=protocol["workers"], mp_context=context
    ) as executor:
        pending = {}
        while True:
            while (
                not stopped
                and time.time() < deadline
                and len(pending) < protocol["workers"]
            ):
                row = next(rows, None)
                if row is None:
                    break
                future = executor.submit(
                    execute_episode,
                    row,
                    problems[row["problem_id"]],
                    str(output),
                    ledger,
                    key_file,
                    deadline,
                    protocol["allowance_usd"],
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
                    result = reconcile_worker_error(
                        row, output, store, type(exc).__name__
                    )
                    stopped = True
                results.append(result)
                if result["status"] != "complete":
                    stopped = True
            manifest.update(
                completed=len(results),
                elapsed_seconds=time.time() - started,
                accounted_cost_delta_usd=store.budget("research")["charged_usd"]
                - initial_budget["charged_usd"],
            )
            write(output / "manifest.json", manifest)
    observed = {r["id"] for r in results}
    missing = [r for r in protocol["study_order"] if r["id"] not in observed]
    manifest.update(
        status="complete" if not missing and not stopped else "incomplete",
        finished_at=utc_now(),
        missing=missing,
        budget_after=store.budget("research"),
    )
    write(output / "manifest.json", manifest)
    print(
        json.dumps(
            {
                key: manifest[key]
                for key in (
                    "status",
                    "completed",
                    "planned",
                    "accounted_cost_delta_usd",
                )
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--ledger")
    parser.add_argument("--key-file")
    parser.add_argument("--expected-protocol-sha256")
    args = parser.parse_args()
    if args.command == "freeze":
        freeze(args.output)
    else:
        if not args.ledger or not args.key_file or not args.expected_protocol_sha256:
            parser.error(
                "run requires --ledger, --key-file and --expected-protocol-sha256"
            )
        run(args.output, args.ledger, args.key_file, args.expected_protocol_sha256)
