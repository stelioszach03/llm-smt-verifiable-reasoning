"""Synthetic journals exercise accounting; they are not model-run evidence."""

import copy
import importlib.util
import json
import math
import io
from pathlib import Path
import tarfile

import pytest


source = Path(__file__).resolve().parents[1] / "scripts/reconcile_pilot_transport.py"
spec = importlib.util.spec_from_file_location("transport_reconciliation", source)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def protocol():
    return {
        "model": "openai/gpt-oss-20b",
        "provider": {
            "only": ["coreweave/fp4"],
            "allow_fallbacks": False,
            "require_parameters": True,
            "quantizations": ["fp4"],
            "max_price": {"prompt": 0.05, "completion": 0.25},
        },
        "temperature": 0.2,
        "max_output_tokens": 2048,
        "reasoning_effort": "low",
        "max_rounds": 4,
        "per_round_candidates": 4,
        "witness_policy": "withhold",
    }


def pair(
    plan,
    identity,
    *,
    call=1,
    ordinal=1,
    retry=0,
    cost=0.0000012,
    tokens=(20, 10, 30),
    status=200,
    reserved=900,
):
    payload = {
        "model": plan["model"],
        "provider": copy.deepcopy(plan["provider"]),
        "temperature": plan["temperature"],
        "max_tokens": plan["max_output_tokens"],
        "reasoning": {"effort": "low"},
        "seed": audit.seed_for(identity["problem_id"], identity["seed"], ordinal),
        "response_format": audit.expected_response_format(),
        "messages": [{"role": "user", "content": "Synthetic unit-test prompt"}],
    }
    request = {
        "type": "request",
        "call": call,
        "ordinal": ordinal,
        "retry": retry,
        "started_at_unix": 1_800_000_000,
        "reserved_micro_usd": reserved,
        "payload": payload,
    }
    visible = (
        None
        if status != 200
        else {
            "model": plan["model"],
            "provider": "CoreWeave",
            "usage": {
                "prompt_tokens": tokens[0],
                "completion_tokens": tokens[1],
                "total_tokens": tokens[2],
                "cost": cost,
            },
            "choices": [{"message": {"content": "{}"}}],
        }
    )
    known = visible is not None and cost is not None
    response = {
        "type": "response",
        "call": call,
        "ordinal": ordinal,
        "retry": retry,
        "http_status": status,
        "error": None
        if status == 200
        else "transport_or_json_error"
        if status is None
        else f"http_{status}",
        "elapsed_ms": 10.0,
        "response": visible,
        "cost_known": known,
        "accounted_micro_usd": math.ceil(cost * 1e6) if known else reserved,
    }
    return [request, response]


def episode(tmp_path, configurations, *, status="stopped", outcome=None):
    plan = protocol()
    identity = {
        "id": "fixture",
        "problem_id": "fixture-problem",
        "seed": 17,
        "arm": "multi_no_feedback",
    }
    events = []
    for index, config in enumerate(configurations, 1):
        events.extend(pair(plan, identity, call=index, **config))
    responses = events[1::2]
    costs = [e["response"]["usage"]["cost"] for e in responses if e["cost_known"]]
    row = {
        **identity,
        "status": status,
        "outcome": outcome,
        "provider_calls": len(responses),
        "known_cost_calls": len(costs),
        "uncertain_calls": len(responses) - len(costs),
        "transport_errors": sum(e["error"] is not None for e in responses),
        "accounted_cost_usd": sum(e["accounted_micro_usd"] for e in responses) / 1e6,
        "provider_reported_cost_usd": sum(costs) if costs else None,
    }
    directory = tmp_path / "fixture"
    directory.mkdir()
    path = directory / "events.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in events))
    return plan, row, events, directory


def overwrite_events(directory, events):
    (directory / "events.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events)
    )


def test_stopped_episode_tokens_are_measured_from_events_without_outcome(tmp_path):
    plan, row, _, directory = episode(tmp_path, [{}])
    result, calls = audit.reconcile_episode(directory, row, plan)
    assert (
        result["original_episode_status"] == "stopped"
        and result["outcome_available"] is False
    )
    assert result["tokens"]["total_tokens"]["all_calls_total"] == 30
    assert result["known_cost_rounding_usd"] == pytest.approx(0.0000008)
    assert result["retained_uncertain_reserve_usd"] == 0
    assert row["outcome"] is None and row["status"] == "stopped"


def test_all_unknown_cost_and_usage_never_become_zero(tmp_path):
    plan, row, _, directory = episode(tmp_path, [{"status": None}])
    result, _ = audit.reconcile_episode(directory, row, plan)
    assert result["provider_reported_known_subtotal_usd"] is None
    assert result["provider_reported_all_calls_usd"] is None
    assert result["known_cost_rounding_usd"] is None
    assert result["retained_uncertain_reserve_usd"] == 0.0009
    assert result["tokens"]["total_tokens"] == {
        "all_calls_total": None,
        "known_subtotal": None,
        "measured_calls": 0,
        "unknown_calls": 1,
    }


def test_mixed_calls_separate_ceil_rounding_from_retained_reserve(tmp_path):
    plan, row, _, directory = episode(tmp_path, [{}, {"ordinal": 2, "status": None}])
    result, _ = audit.reconcile_episode(directory, row, plan)
    assert result["accounted_micro_usd"] == 902
    assert result["known_cost_rounding_usd"] == pytest.approx(0.0000008)
    assert result["retained_uncertain_reserve_micro_usd"] == 900
    assert result["provider_reported_known_subtotal_usd"] == 0.0000012
    assert result["tokens"]["total_tokens"]["known_subtotal"] == 30
    assert result["tokens"]["total_tokens"]["all_calls_total"] is None


def test_zero_reported_charge_is_known_not_unknown(tmp_path):
    plan, row, _, directory = episode(tmp_path, [{"cost": 0.0, "tokens": (0, 0, 0)}])
    result, _ = audit.reconcile_episode(directory, row, plan)
    assert result["known_cost_calls"] == 1 and result["uncertain_cost_calls"] == 0
    assert result["provider_reported_all_calls_usd"] == 0
    assert result["tokens"]["total_tokens"]["all_calls_total"] == 0


def test_missing_total_tokens_not_inferred_from_known_parts(tmp_path):
    plan, row, _, directory = episode(tmp_path, [{"tokens": (20, 10, None)}])
    result, _ = audit.reconcile_episode(directory, row, plan)
    assert result["tokens"]["prompt_tokens"]["all_calls_total"] == 20
    assert result["tokens"]["total_tokens"]["all_calls_total"] is None


def test_all_retry_requests_are_counted_with_unknown_usage_retained(tmp_path):
    plan, row, _, directory = episode(tmp_path, [{"status": 429}, {"retry": 1}])
    result, _ = audit.reconcile_episode(directory, row, plan)
    assert result["provider_calls"] == 2
    assert result["generated_ordinals_with_actual_requests"] == 1
    assert result["tokens"]["total_tokens"]["known_subtotal"] == 30
    assert result["tokens"]["total_tokens"]["all_calls_total"] is None


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_response",
        "duplicate_response",
        "cost",
        "wrong_provider",
        "seed",
        "config",
        "result_calls",
        "invalid_token_sum",
        "cost_flag",
        "retry_payload",
    ],
)
def test_discrepancies_fail_closed(tmp_path, mutation):
    plan, row, events, directory = episode(
        tmp_path,
        [{"status": 429}, {"retry": 1}] if mutation == "retry_payload" else [{}],
    )
    if mutation == "missing_response":
        events.pop()
    elif mutation == "duplicate_response":
        events.append(copy.deepcopy(events[-1]))
    elif mutation == "cost":
        events[-1]["accounted_micro_usd"] += 1
    elif mutation == "wrong_provider":
        events[-1]["response"]["provider"] = "Different"
    elif mutation == "seed":
        events[0]["payload"]["seed"] += 1
    elif mutation == "config":
        events[0]["payload"]["temperature"] = 0.8
    elif mutation == "result_calls":
        row["provider_calls"] += 1
    elif mutation == "invalid_token_sum":
        events[-1]["response"]["usage"]["total_tokens"] = 29
    elif mutation == "cost_flag":
        events[-1]["cost_known"] = False
    elif mutation == "retry_payload":
        events[2]["payload"]["messages"][0]["content"] += "changed"
    overwrite_events(directory, events)
    with pytest.raises(ValueError):
        audit.reconcile_episode(directory, row, plan)


def test_full_outcome_usage_reconciles_generated_and_evaluated_evidence(tmp_path):
    generated = {
        "round_index": 1,
        "candidate_index": 0,
        "prompt_tokens": 20,
        "completion_tokens": 10,
        "total_tokens": 30,
    }
    outcome = {
        "witness_policy": "withhold",
        "generated_candidates": [generated],
        "llm_attempts": 1,
        "known_prompt_tokens": 20,
        "known_completion_tokens": 10,
        "known_total_tokens": 30,
        "prompt_tokens": 20,
        "completion_tokens": 10,
        "total_tokens": 30,
        "usage_measurements": {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 1,
        },
        "usage_complete": True,
    }
    plan, row, _, directory = episode(
        tmp_path, [{}], status="complete", outcome=outcome
    )
    audit.reconcile_episode(directory, row, plan)
    row["outcome"]["total_tokens"] = 29
    with pytest.raises(ValueError, match="aggregate token"):
        audit.reconcile_episode(directory, row, plan)


def test_nonfinite_evidence_rejected():
    with pytest.raises(ValueError, match="Nonfinite"):
        audit.strict_json('{"cost":NaN}')


def test_zero_actual_calls_are_zero_arithmetic_not_unknown_calls():
    result = audit.aggregate_calls([])
    assert result["provider_calls"] == 0
    assert result["tokens"]["total_tokens"]["unknown_calls"] == 0
    assert result["tokens"]["total_tokens"]["all_calls_total"] == 0


def test_archive_members_match_without_extraction(tmp_path):
    source_bytes = b"actual immutable evidence\n"
    target = tmp_path / "snapshot.tar.gz"
    with tarfile.open(target, "w:gz") as archive:
        entry = tarfile.TarInfo("./episodes/fixture/events.jsonl")
        entry.size = len(source_bytes)
        archive.addfile(entry, io.BytesIO(source_bytes))
    import hashlib

    expected = {
        "episodes/fixture/events.jsonl": hashlib.sha256(source_bytes).hexdigest()
    }
    assert audit.verify_archive_sources(target, expected) == 1
    assert list(tmp_path.iterdir()) == [target]
    with pytest.raises(ValueError, match="differs"):
        audit.verify_archive_sources(
            target, {"episodes/fixture/events.jsonl": "0" * 64}
        )
    with pytest.raises(ValueError, match="absent"):
        audit.verify_archive_sources(target, {**expected, "missing.json": "0" * 64})
