#!/usr/bin/env python3
"""Reconcile immutable CEGVR transport evidence without changing outcomes.

Reads request/response journals, including deadline-stopped episodes. No ledger,
credentials, network, model calls, solver calls or runtime imports are used.
"""

from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
import hashlib
from itertools import product
import json
import math
from pathlib import Path
import tarfile

TOKEN_FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens")
MICRO = Decimal(1_000_000)


def fail(message):
    raise ValueError(message)


def strict_json(text):
    def invalid(value):
        fail("Nonfinite JSON literal in evidence")

    return json.loads(text, parse_constant=invalid)


def read(path):
    return strict_json(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def integer(value, label, *, minimum=0, nullable=False):
    if value is None and nullable:
        return None
    if type(value) is not int or value < minimum:
        fail(f"Invalid integer: {label}")
    return value


def numeric(value, label, *, nullable=False):
    if value is None and nullable:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        fail(f"Invalid nonnegative finite number: {label}")
    return value


def seed_for(problem_id, repeat, ordinal):
    value = f"cegvr-pilot-v1|{problem_id}|{repeat}|{ordinal}".encode()
    return int(hashlib.sha256(value).hexdigest()[:8], 16) & 0x7FFFFFFF


def expected_response_format():
    # Original candidate schema after the frozen provider adapter removes its
    # unsupported if/then allOf. Strict local SAT/UNSAT parsing is separate.
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "candidate_output",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["status"],
                "properties": {
                    "status": {"type": "string", "enum": ["sat", "unsat"]},
                    "assignment": {
                        "type": "object",
                        "additionalProperties": {
                            "oneOf": [{"type": "integer"}, {"type": "boolean"}]
                        },
                    },
                    "unsat_explanation": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                },
            },
        },
    }


def validate_request(event, result, protocol):
    payload = event.get("payload")
    if not isinstance(payload, dict):
        fail("Missing request payload")
    expected = {
        "model": protocol["model"],
        "provider": protocol["provider"],
        "temperature": protocol["temperature"],
        "max_tokens": protocol["max_output_tokens"],
        "reasoning": {"effort": protocol["reasoning_effort"]},
        "seed": seed_for(result["problem_id"], result["seed"], event["ordinal"]),
        "response_format": expected_response_format(),
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        fail("Request model/provider/decoding/seed/schema differs from frozen protocol")
    if set(payload) != set(expected) | {"messages"}:
        fail("Unexpected request payload fields")
    if not isinstance(payload["messages"], list) or not payload["messages"]:
        fail("Missing actual prompt messages")
    integer(event.get("reserved_micro_usd"), "reserved_micro_usd", minimum=1)
    numeric(event.get("started_at_unix"), "started_at_unix")
    return payload


def validate_response(request, response, protocol):
    if any(response.get(key) != request[key] for key in ("call", "ordinal", "retry")):
        fail("Response does not match its request identity")
    status = response.get("http_status")
    if status is not None and (type(status) is not int or not 100 <= status <= 599):
        fail("Invalid HTTP status")
    if response.get("error") is not None and not isinstance(response["error"], str):
        fail("Invalid transport error field")
    elapsed = numeric(response.get("elapsed_ms"), "elapsed_ms")
    visible = response.get("response")
    usage, identity_confirmed = {}, False
    if visible is not None:
        if not isinstance(visible, dict):
            fail("Invalid visible response shape")
        if (
            visible.get("model") != protocol["model"]
            or visible.get("provider") != "CoreWeave"
        ):
            fail(
                "Returned model/provider identity mismatch or unavailable in a recorded response"
            )
        identity_confirmed = True
        usage = visible.get("usage")
        if not isinstance(usage, dict):
            fail("Invalid usage shape")
    elif status == 200 and response.get("error") is None:
        fail("HTTP 200 with no response and no recorded error")
    tokens = {key: integer(usage.get(key), key, nullable=True) for key in TOKEN_FIELDS}
    if (
        all(value is not None for value in tokens.values())
        and tokens["total_tokens"]
        < tokens["prompt_tokens"] + tokens["completion_tokens"]
    ):
        fail("Reported total tokens are less than prompt plus completion")
    known_cost = numeric(usage.get("cost"), "provider cost", nullable=True)
    known = response.get("cost_known")
    if type(known) is not bool or known != (known_cost is not None):
        fail("Recorded cost-known flag differs from actual cost evidence")
    accounted = integer(response.get("accounted_micro_usd"), "accounted_micro_usd")
    reserved = request["reserved_micro_usd"]
    expected_charge = math.ceil(known_cost * 1e6) if known else reserved
    if accounted != expected_charge or accounted > reserved:
        fail(
            "Accounted charge differs from frozen ceil/reserve accounting or exceeds reservation"
        )
    reported_decimal = Decimal(str(known_cost)) if known else None
    rounding_decimal = Decimal(accounted) / MICRO - reported_decimal if known else None
    # Tiny negative binary-conversion margins must never masquerade as reserves.
    if rounding_decimal is not None and rounding_decimal < Decimal("-1e-15"):
        fail("Known cost rounding is materially negative")
    return {
        "call": request["call"],
        "ordinal": request["ordinal"],
        "retry": request["retry"],
        "http_status": status,
        "transport_error": response.get("error"),
        "returned_identity_confirmed": identity_confirmed,
        "reserved_micro_usd": reserved,
        "accounted_micro_usd": accounted,
        "reported_cost_decimal": reported_decimal,
        "rounding_decimal": rounding_decimal,
        "retained_reserve_micro_usd": 0 if known else reserved,
        "tokens": tokens,
        "http_elapsed_ms": elapsed,
    }


def money(value):
    return None if value is None else float(value)


def aggregate_calls(calls):
    known = [row for row in calls if row["reported_cost_decimal"] is not None]
    measured_cost = sum((row["reported_cost_decimal"] for row in known), Decimal(0))
    known_rounding = sum((row["rounding_decimal"] for row in known), Decimal(0))
    accounted = sum(row["accounted_micro_usd"] for row in calls)
    retained = sum(row["retained_reserve_micro_usd"] for row in calls)
    if (
        Decimal(accounted) / MICRO
        != measured_cost + known_rounding + Decimal(retained) / MICRO
    ):
        fail("Cost components do not reconcile exactly")
    usage = {}
    for field in TOKEN_FIELDS:
        measured = [
            row["tokens"][field] for row in calls if row["tokens"][field] is not None
        ]
        usage[field] = {
            "measured_calls": len(measured),
            "unknown_calls": len(calls) - len(measured),
            "known_subtotal": sum(measured) if measured else (0 if not calls else None),
            "all_calls_total": sum(measured) if len(measured) == len(calls) else None,
        }
    return {
        "provider_calls": len(calls),
        "paired_responses": len(calls),
        "returned_identity_confirmed_calls": sum(
            r["returned_identity_confirmed"] for r in calls
        ),
        "returned_identity_unavailable_calls": sum(
            not r["returned_identity_confirmed"] for r in calls
        ),
        "http_status_counts": dict(
            sorted(
                Counter(
                    "unavailable" if r["http_status"] is None else str(r["http_status"])
                    for r in calls
                ).items()
            )
        ),
        "transport_error_calls": sum(r["transport_error"] is not None for r in calls),
        "known_cost_calls": len(known),
        "uncertain_cost_calls": len(calls) - len(known),
        "accounted_micro_usd": accounted,
        "accounted_cost_usd": accounted / 1e6,
        "provider_reported_known_subtotal_usd": money(measured_cost)
        if known
        else (0.0 if not calls else None),
        "provider_reported_all_calls_usd": money(measured_cost)
        if len(known) == len(calls)
        else None,
        "known_cost_rounding_usd": money(known_rounding)
        if known
        else (0.0 if not calls else None),
        "known_cost_rounding_usd_decimal": str(known_rounding)
        if known
        else ("0" if not calls else None),
        "retained_uncertain_reserve_micro_usd": retained,
        "retained_uncertain_reserve_usd": retained / 1e6,
        "cost_component_identity": "accounted = provider-reported known subtotal + known ceil rounding + retained uncertain reservations",
        "tokens": usage,
        "summed_http_elapsed_ms": sum(r["http_elapsed_ms"] for r in calls),
    }


def reconcile_episode(directory, result, protocol):
    path = directory / "events.jsonl"
    events = (
        [strict_json(line) for line in path.read_text().splitlines()]
        if path.exists()
        else []
    )
    requests, responses, calls, previous = {}, {}, [], None
    for event in events:
        kind = event.get("type")
        call = integer(event.get("call"), "call", minimum=1)
        ordinal = integer(event.get("ordinal"), "ordinal", minimum=1)
        retry = integer(event.get("retry"), "retry")
        if retry > 2:
            fail("Transport retry exceeds frozen cap")
        if kind == "request":
            if call != len(requests) + 1 or len(requests) != len(responses):
                fail("Nonsequential/duplicate/unpaired request journal")
            payload = validate_request(event, result, protocol)
            if previous is None:
                if ordinal != 1 or retry != 0:
                    fail("First request ordinal/retry is invalid")
            elif ordinal == previous["ordinal"]:
                if (
                    retry != previous["retry"] + 1
                    or responses[previous["call"]].get("http_status") != 429
                    or payload != previous["payload"]
                ):
                    fail("Retry is not an identical-payload HTTP429 retry")
            elif ordinal != previous["ordinal"] + 1 or retry != 0:
                fail("Skipped or repeated candidate ordinal")
            requests[call], previous = event, event
        elif kind == "response":
            if call in responses or call not in requests or call != len(responses) + 1:
                fail("Nonsequential/duplicate/orphan response journal")
            responses[call] = event
            calls.append(validate_response(requests[call], event, protocol))
        else:
            fail("Unexpected journal event type")
    if set(requests) != set(responses):
        fail("Unpaired requests remain; no missing response usage is inferred")
    measured = aggregate_calls(calls)
    ordinal_cap = (
        1
        if result["arm"] == "one_shot"
        else protocol["max_rounds"] * protocol["per_round_candidates"]
    )
    ordinals = {r["ordinal"] for r in calls}
    if len(ordinals) > ordinal_cap:
        fail("Candidate generation exceeds frozen arm budget")
    if integer(result.get("provider_calls"), "result provider_calls") != len(calls):
        fail("Result provider-call count differs from actual paired events")
    if not math.isclose(
        numeric(result.get("accounted_cost_usd"), "result accounted cost"),
        measured["accounted_cost_usd"],
        abs_tol=1e-12,
        rel_tol=0,
    ):
        fail("Result accounted cost differs from transport sum")
    recorded_known = numeric(
        result.get("provider_reported_cost_usd"), "result known cost", nullable=True
    )
    event_known = measured["provider_reported_known_subtotal_usd"]
    # Zero actual calls have no provider invoice/usage measurement in the runtime.
    if not calls:
        if recorded_known is not None:
            fail("Zero-call result must not claim a provider cost measurement")
    elif event_known is None:
        if recorded_known is not None:
            fail("All-unknown provider costs must remain null")
    elif recorded_known is None or not math.isclose(
        recorded_known, event_known, abs_tol=1e-12, rel_tol=0
    ):
        fail("Result provider-reported cost does not reconcile")
    for field, expected in (
        ("uncertain_calls", measured["uncertain_cost_calls"]),
        ("transport_errors", measured["transport_error_calls"]),
    ):
        if integer(result.get(field), field) != expected:
            fail("Result error/uncertainty counts differ from events")
    if (
        "known_cost_calls" in result
        and integer(result["known_cost_calls"], "known_cost_calls")
        != measured["known_cost_calls"]
    ):
        fail("Result known-cost coverage differs from events")
    outcome = result.get("outcome")
    if outcome is not None:
        if outcome.get("witness_policy") != protocol["witness_policy"]:
            fail("Outcome witness policy differs from freeze")
        generated = outcome.get("generated_candidates")
        if (
            not isinstance(generated, list)
            or len(generated) != len(ordinals)
            or outcome.get("llm_attempts") != len(generated)
        ):
            fail("Outcome generated candidate counts differ from request ordinals")
        final_by_ordinal = {row["ordinal"]: row for row in calls}
        width = 1 if result["arm"] == "one_shot" else protocol["per_round_candidates"]
        seen = set()
        for row in generated:
            ordinal = (row["round_index"] - 1) * width + row["candidate_index"] + 1
            if ordinal in seen or ordinal not in final_by_ordinal:
                fail("Generated candidate identity does not reconcile")
            seen.add(ordinal)
            if any(
                row.get(key) != final_by_ordinal[ordinal]["tokens"][key]
                for key in TOKEN_FIELDS
            ):
                fail(
                    "Generated candidate usage differs from its final provider response"
                )
        for key in TOKEN_FIELDS:
            values = [row[key] for row in generated if row.get(key) is not None]
            if outcome.get("known_" + key) != sum(values) or outcome.get(
                "usage_measurements", {}
            ).get(key) != len(values):
                fail("Outcome measured token subtotals differ from candidate evidence")
            expected = sum(values) if len(values) == len(generated) else None
            if outcome.get(key) != expected:
                fail("Outcome aggregate token total has incorrect missingness or value")
        expected_complete = all(
            all(row.get(key) is not None for key in TOKEN_FIELDS) for row in generated
        )
        if outcome.get("usage_complete") is not expected_complete:
            fail("Outcome usage-completeness flag differs from generated evidence")
    return {
        "id": result["id"],
        "problem_id": result["problem_id"],
        "seed": result["seed"],
        "arm": result["arm"],
        "original_episode_status": result["status"],
        "outcome_available": outcome is not None,
        "generated_ordinals_with_actual_requests": len(ordinals),
        **measured,
    }, calls


def reconcile(study, expected_protocol_sha=None):
    study = Path(study).resolve()
    protocol, manifest = read(study / "protocol.json"), read(study / "manifest.json")
    protocol_sha = sha(study / "protocol.json")
    if (
        manifest.get("protocol_sha256") != protocol_sha
        or expected_protocol_sha is not None
        and protocol_sha != expected_protocol_sha
    ):
        fail("Original frozen protocol hash does not reconcile")
    if manifest.get("status") not in ("complete", "incomplete") or not manifest.get(
        "finished_at"
    ):
        fail("Use a finalized immutable snapshot, not a running study")
    expected = {r["id"]: r for r in protocol["study_order"]}
    expected_keys = {(r["problem_id"], r["seed"], r["arm"]) for r in expected.values()}
    labels = {r["problem_id"]: r["ground_truth"] for r in protocol["selected_tasks"]}
    if (
        len(expected) != len(protocol["study_order"])
        or len(expected_keys) != len(expected)
        or expected_keys != set(product(labels, protocol["seeds"], protocol["arms"]))
    ):
        fail("Frozen episode matrix is incomplete or duplicated")
    episodes, all_calls, seen = [], [], set()
    source_hashes = {
        "protocol.json": protocol_sha,
        "manifest.json": sha(study / "manifest.json"),
    }
    for directory in sorted((study / "episodes").iterdir()):
        if (
            not directory.is_dir()
            or directory.is_symlink()
            or directory.name not in expected
            or not (directory / "result.json").is_file()
        ):
            fail("Unexpected or partial episode directory")
        result = read(directory / "result.json")
        if (
            result.get("id") != directory.name
            or any(result.get(k) != v for k, v in expected[directory.name].items())
            or result.get("status") not in ("complete", "stopped", "error")
        ):
            fail("Result row differs from original matrix identity")
        try:
            episode, calls = reconcile_episode(directory, result, protocol)
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            raise ValueError(
                f"Episode {directory.name} did not reconcile: {exc}"
            ) from exc
        episodes.append(episode)
        all_calls.extend(
            {**row, "arm": result["arm"], "episode_status": result["status"]}
            for row in calls
        )
        seen.add(directory.name)
        for name in ("result.json", "events.jsonl"):
            path = directory / name
            if path.is_file():
                source_hashes[str(path.relative_to(study))] = sha(path)
    missing = [row for row in protocol["study_order"] if row["id"] not in seen]
    declared_missing = manifest["missing"]
    if (
        manifest["planned"] != len(expected)
        or manifest["completed"] != len(episodes)
        or declared_missing != missing
        or manifest["status"] == "complete"
        and missing
    ):
        fail("Final manifest coverage differs from preserved episode records")
    arms = []
    for arm in protocol["arms"]:
        selected = [row for row in all_calls if row["arm"] == arm]
        arm_episodes = [row for row in episodes if row["arm"] == arm]
        arms.append(
            {
                "arm": arm,
                "episodes": len(arm_episodes),
                "episode_status_counts": dict(
                    Counter(r["original_episode_status"] for r in arm_episodes)
                ),
                **aggregate_calls(selected),
            }
        )
    stopped_calls = [row for row in all_calls if row["episode_status"] == "stopped"]
    report = {
        "schema": "cegvr-pilot-transport-reconciliation-v1",
        "status": "reconciled",
        "scope": "Analysis of immutable request/response evidence only; no ledger access, new inference, outcome changes or regrading",
        "original_study_status": manifest["status"],
        "planned_episodes": len(expected),
        "observed_episodes": len(episodes),
        "missing_unlaunched_episodes": len(missing),
        "episode_status_counts": dict(
            Counter(r["original_episode_status"] for r in episodes)
        ),
        "overall": aggregate_calls(all_calls),
        "per_arm": arms,
        "stopped_episode_count": sum(
            r["original_episode_status"] == "stopped" for r in episodes
        ),
        "stopped_episode_transport": aggregate_calls(stopped_calls),
        "episodes": episodes,
        "interpretation": "Tokens come from all recorded provider attempts, including deadline-stopped episodes without a completed outcome. Unknown calls stay unknown. Known ceil rounding is distinct from conservatively retained uncertain reservations; costs are provider usage reports, not invoices, and exclude credit fees. Summed HTTP elapsed time is not wall-clock study duration or GPU time. Existing episode outcomes remain unchanged.",
        "protocol_sha256": protocol_sha,
        "analysis_source_sha256": sha(Path(__file__)),
        "source_file_sha256": source_hashes,
    }
    if any(sha(study / name) != value for name, value in source_hashes.items()):
        fail("Source evidence changed during reconciliation")
    return report


def verify_archive_sources(archive_path, source_hashes):
    """Verify exact source members by streaming, never extracting or overwriting."""
    seen = set()
    with tarfile.open(archive_path, mode="r|gz") as archive:
        for member in archive:
            name = member.name.removeprefix("./")
            if name not in source_hashes:
                continue
            if name in seen or not member.isfile():
                fail("Duplicate or nonregular source member in archived snapshot")
            stream = archive.extractfile(member)
            measured = hashlib.sha256()
            for block in iter(lambda stream=stream: stream.read(1024 * 1024), b""):
                measured.update(block)
            if measured.hexdigest() != source_hashes[name]:
                fail("Analyzed evidence differs from the original archived member")
            seen.add(name)
    if seen != set(source_hashes):
        fail("Some analyzed source files are absent from the original archive")
    return len(seen)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-protocol-sha256")
    parser.add_argument("--source-archive", type=Path)
    parser.add_argument("--expected-archive-sha256")
    args = parser.parse_args(argv)
    if (
        args.output.resolve() == args.study.resolve()
        or args.study.resolve() in args.output.resolve().parents
    ):
        parser.error("Write the supplement outside the immutable study directory")
    if bool(args.source_archive) != bool(args.expected_archive_sha256):
        parser.error(
            "Archive provenance requires both path and externally recorded SHA256"
        )
    if args.source_archive and sha(args.source_archive) != args.expected_archive_sha256:
        fail("Archived first-wave snapshot hash mismatch")
    report = reconcile(args.study, args.expected_protocol_sha256)
    if args.source_archive:
        report["source_archive_sha256"] = args.expected_archive_sha256
        report["source_archive_members_verified"] = verify_archive_sources(
            args.source_archive, report["source_file_sha256"]
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "episodes": report["observed_episodes"],
                "provider_calls": report["overall"]["provider_calls"],
                "output": str(args.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
