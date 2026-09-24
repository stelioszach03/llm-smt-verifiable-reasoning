#!/usr/bin/env python3
"""Describe real, reconciled CEGVR pilot episodes without fabricating missing cells."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
from itertools import combinations, product
import json
import math
from pathlib import Path


def number(value, name, *, integer=False, nullable=False):
    if value is None and nullable:
        return None
    if (
        type(value) not in ((int,) if integer else (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(
            f"Invalid nonnegative {'integer' if integer else 'number'}: {name}"
        )
    return value


def identity(row):
    return (row["problem_id"], row["seed"], row["arm"])


def read_study(root):
    protocol = json.loads((root / "protocol.json").read_text())
    manifest = json.loads((root / "manifest.json").read_text())
    tasks, seeds, arms = protocol["selected_tasks"], protocol["seeds"], protocol["arms"]
    labels = {row["problem_id"]: row["ground_truth"] for row in tasks}
    if (
        len(labels) != len(tasks)
        or not labels
        or set(labels.values()) - {"sat", "unsat"}
        or len(set(seeds)) != len(seeds)
        or not seeds
        or any(type(seed) is not int for seed in seeds)
        or len(set(arms)) != len(arms)
        or not arms
    ):
        raise ValueError("Invalid or duplicate declared task/seed/arm matrix")
    expected = {row["id"]: row for row in protocol["study_order"]}
    expected_keys = {identity(row) for row in expected.values()}
    if (
        len(expected) != len(protocol["study_order"])
        or len(expected_keys) != len(expected)
        or expected_keys != set(product(labels, seeds, arms))
        or any(
            row["ground_truth"] != labels[row["problem_id"]]
            for row in expected.values()
        )
    ):
        raise ValueError(
            "Frozen study_order is not the declared complete Cartesian matrix"
        )
    records, seen = [], set()
    for path in sorted((root / "episodes").glob("*/result.json")):
        row = json.loads(path.read_text())
        key = row["id"]
        if (
            key not in expected
            or key in seen
            or path.parent.name != key
            or any(
                row[name] != expected[key][name]
                for name in ("problem_id", "ground_truth", "seed", "arm")
            )
            or row["status"] not in ("complete", "stopped", "error")
        ):
            raise ValueError("Unexpected, duplicate or mixed episode record")
        seen.add(key)
        records.append(row)
    missing = [row for key, row in expected.items() if key not in seen]
    declared_missing = [
        row["id"] if isinstance(row, dict) else row for row in manifest["missing"]
    ]
    if (
        manifest["planned"] != len(expected)
        or manifest["completed"] != len(records)
        or len(declared_missing) != len(missing)
        or set(declared_missing) != {row["id"] for row in missing}
        or manifest["status"] == "complete"
        and missing
    ):
        raise ValueError("Manifest planned/completed/missing matrix does not reconcile")
    return protocol, manifest, records, missing


def metrics(record):
    outcome = record.get("outcome") or {}
    if not isinstance(outcome, dict):
        raise ValueError("Outcome must be an object or null")
    certificate = outcome.get("verified_outcome")
    expected_certificate = (
        "CERTIFIED_SAT" if record["ground_truth"] == "sat" else "CERTIFIED_UNSAT"
    )
    if (
        certificate in ("CERTIFIED_SAT", "CERTIFIED_UNSAT")
        and certificate != expected_certificate
    ):
        raise ValueError(
            "Candidate certificate contradicts declared solver ground truth"
        )
    success = (
        record["status"] == "complete"
        and outcome.get("status") == "certified"
        and certificate == expected_certificate
    )
    if outcome and outcome.get("witness_policy") != "withhold":
        raise ValueError(
            "Mixed or unspecified solver-witness policy in primary candidate study"
        )
    known_cost = number(
        record.get("provider_reported_cost_usd"),
        "provider_reported_cost_usd",
        nullable=True,
    )
    accounted = number(record["accounted_cost_usd"], "accounted_cost_usd")
    if known_cost is not None and known_cost > accounted + 1e-6:
        raise ValueError("Provider-reported cost exceeds accounted cost")
    total_tokens = (
        outcome.get("total_tokens") if outcome.get("usage_complete") is True else None
    )
    number(total_tokens, "total_tokens", integer=True, nullable=True)
    generated = outcome.get("generated_candidates")
    generated_count = len(generated) if isinstance(generated, list) else None
    evaluated = outcome.get("evaluated_candidates")
    unused = outcome.get("unevaluated_candidates")
    if generated_count is not None:
        number(evaluated, "evaluated_candidates", integer=True)
        number(unused, "unevaluated_candidates", integer=True)
        if evaluated + unused != generated_count:
            raise ValueError(
                "Generated/evaluated/unevaluated candidate counts disagree"
            )
    return {
        "id": record["id"],
        "problem_id": record["problem_id"],
        "ground_truth": record["ground_truth"],
        "seed": record["seed"],
        "arm": record["arm"],
        "episode_status": record["status"],
        "success": int(success),
        "verified_outcome": certificate,
        "predicted_status": outcome.get("predicted_status"),
        "provider_calls": number(
            record["provider_calls"], "provider_calls", integer=True
        ),
        "accounted_cost_usd": accounted,
        "provider_reported_cost_usd": known_cost,
        "unconfirmed_reserve_usd": max(0.0, accounted - (known_cost or 0.0)),
        "uncertain_calls": number(
            record["uncertain_calls"], "uncertain_calls", integer=True
        ),
        "transport_errors": number(
            record["transport_errors"], "transport_errors", integer=True
        ),
        "wall_latency_ms": number(
            record["wall_latency_ms"],
            "wall_latency_ms",
            nullable=record["status"] == "error",
        ),
        "total_tokens": total_tokens,
        "generated_candidates": generated_count,
        "evaluated_candidates": evaluated,
        "unevaluated_candidates": unused,
        "solver_calls": outcome.get("solver_calls"),
        "rounds": outcome.get("rounds"),
        "error": record.get("error"),
    }


def summarize(rows, planned, arm, stratum):
    chosen = [
        row
        for row in rows
        if row["arm"] == arm and (stratum == "all" or row["ground_truth"] == stratum)
    ]
    expected = [
        row
        for row in planned
        if row["arm"] == arm and (stratum == "all" or row["ground_truth"] == stratum)
    ]
    n = len(chosen)
    successes = sum(row["success"] for row in chosen)
    known = [
        row["provider_reported_cost_usd"]
        for row in chosen
        if row["provider_reported_cost_usd"] is not None
    ]
    tokens = [row["total_tokens"] for row in chosen if row["total_tokens"] is not None]
    latencies = [
        row["wall_latency_ms"] for row in chosen if row["wall_latency_ms"] is not None
    ]
    return {
        "arm": arm,
        "stratum": stratum,
        "planned": len(expected),
        "observed": n,
        "unlaunched_missing": len(expected) - n,
        "observed_problem_count": len({row["problem_id"] for row in chosen}),
        "complete_matrix_coverage": n == len(expected),
        "certified_successes": successes,
        "observed_success_rate": successes / n if n else None,
        "complete_matrix_success_rate": successes / len(expected)
        if expected and n == len(expected)
        else None,
        "status_counts": dict(Counter(row["episode_status"] for row in chosen)),
        "final_outcome_counts": dict(
            Counter(row["verified_outcome"] or "unavailable" for row in chosen)
        ),
        "provider_calls_total": sum(row["provider_calls"] for row in chosen),
        "transport_errors_total": sum(row["transport_errors"] for row in chosen),
        "uncertain_calls_total": sum(row["uncertain_calls"] for row in chosen),
        "accounted_cost_usd_total": sum(row["accounted_cost_usd"] for row in chosen),
        "mean_accounted_cost_usd_per_observed_episode": sum(
            row["accounted_cost_usd"] for row in chosen
        )
        / n
        if n
        else None,
        "provider_reported_cost_usd_known_subtotal": sum(known) if known else None,
        "episodes_with_reported_cost_field": len(known),
        "unconfirmed_reserve_usd_total": sum(
            row["unconfirmed_reserve_usd"] for row in chosen
        ),
        "episodes_with_measured_wall_latency": len(latencies),
        "mean_wall_latency_ms": sum(latencies) / len(latencies) if latencies else None,
        "episodes_with_complete_token_usage": len(tokens),
        "mean_tokens_measured_episodes_only": sum(tokens) / len(tokens)
        if tokens
        else None,
        "total_tokens_all_observed_episodes": sum(tokens)
        if n and len(tokens) == n
        else None,
        "mean_accounted_cost_per_certified_success": sum(
            row["accounted_cost_usd"] for row in chosen
        )
        / successes
        if successes
        else None,
        "unevaluated_generated_candidates_known_subtotal": sum(
            row["unevaluated_candidates"]
            for row in chosen
            if row["unevaluated_candidates"] is not None
        ),
    }


def analyze(root):
    protocol, manifest, records, missing = read_study(root)
    rows = [metrics(row) for row in records]
    planned = protocol["study_order"]
    summary = [
        summarize(rows, planned, arm, stratum)
        for stratum in ("sat", "unsat", "all")
        for arm in protocol["arms"]
    ]
    paired = []
    for stratum in ("sat", "unsat", "all"):
        for arm_a, arm_b in combinations(protocol["arms"], 2):
            indexed = {
                arm: {
                    (row["problem_id"], row["seed"]): row
                    for row in rows
                    if row["arm"] == arm
                    and (stratum == "all" or row["ground_truth"] == stratum)
                }
                for arm in (arm_a, arm_b)
            }
            keys = sorted(set(indexed[arm_a]) & set(indexed[arm_b]))
            comparisons = [(indexed[arm_a][key], indexed[arm_b][key]) for key in keys]
            planned_pairs = sum(
                row["arm"] == arm_a
                and (stratum == "all" or row["ground_truth"] == stratum)
                for row in planned
            )
            paired.append(
                {
                    "stratum": stratum,
                    "arm_a": arm_a,
                    "arm_b": arm_b,
                    "planned_pairs": planned_pairs,
                    "observed_pairs": len(keys),
                    "observed_problems": len({key[0] for key in keys}),
                    "missing_pairs": planned_pairs - len(keys),
                    "success_rate_difference_a_minus_b": sum(
                        a["success"] - b["success"] for a, b in comparisons
                    )
                    / len(keys)
                    if keys
                    else None,
                    "wins_a": sum(a["success"] > b["success"] for a, b in comparisons),
                    "wins_b": sum(b["success"] > a["success"] for a, b in comparisons),
                    "equal_success_outcome": sum(
                        a["success"] == b["success"] for a, b in comparisons
                    ),
                    "mean_accounted_cost_difference_a_minus_b": sum(
                        a["accounted_cost_usd"] - b["accounted_cost_usd"]
                        for a, b in comparisons
                    )
                    / len(keys)
                    if keys
                    else None,
                }
            )
    baseline_path = root / "direct_solver.json"
    report = {
        "schema": "cegvr-openrouter-pilot-analysis-v1",
        "study_status": manifest["status"],
        "planned": len(planned),
        "observed": len(rows),
        "missing": missing,
        "primary_endpoint": "SAT complete-candidate certification, evaluated against all encoded constraints; eligible SAT tasks only",
        "secondary_endpoints": [
            "UNSAT claim certification by Z3 (not an LLM-produced proof)",
            "Overall formal certification with the fixed SAT/UNSAT mixture",
        ],
        "summary": summary,
        "paired_descriptive_comparisons": paired,
        "confidence_intervals": None,
        "significance_claim": False,
        "direct_solver_control": json.loads(baseline_path.read_text())
        if baseline_path.exists()
        else None,
        "interpretation": "Descriptive hash-selected pilot from an already public synthetic dataset. STOP/error episodes are observed unsuccessful executions; unlaunched cells remain missing. Paired summaries use shared observed problem/seed identities only, with no independent-seed, causal or significance claim. Certificates concern formal constraints, not natural-language semantics or LLM proof construction. Exact solver witnesses are withheld from primary feedback.",
        "protocol_sha256": hashlib.sha256(
            (root / "protocol.json").read_bytes()
        ).hexdigest(),
        "analysis_source_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "source_file_sha256": {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        },
    }
    return report, rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if (
        args.study.resolve() == args.output.resolve()
        or args.study.resolve() in args.output.resolve().parents
    ):
        parser.error(
            "Analysis must be a separate directory outside the immutable source study"
        )
    report, rows = analyze(args.study)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "analysis.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    if rows:
        with (args.output / "episodes.csv").open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    lines = [
        "# CEGVR OpenRouter pilot - recorded results",
        "",
        f"Coverage: **{report['observed']} / {report['planned']}** frozen episodes; study status: **{report['study_status']}**.",
        "",
        report["interpretation"],
        "",
        "No population confidence interval or statistical-significance claim is reported. Missing metrics remain unmeasured, not zero.",
        "",
    ]
    for stratum, heading in [
        ("sat", "Primary: valid SAT assignments"),
        ("unsat", "Secondary: solver-certified UNSAT claims"),
        ("all", "Secondary: fixed-mixture overall certification"),
    ]:
        lines += [
            "## " + heading,
            "",
            "| Arm | Observed / planned | Certified | Observed rate | Accounted cost / observed | Provider calls |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for row in report["summary"]:
            if row["stratum"] != stratum:
                continue
            rate = (
                f"{row['observed_success_rate']:.1%}"
                if row["observed_success_rate"] is not None
                else "unmeasured"
            )
            cost = (
                f"${row['mean_accounted_cost_usd_per_observed_episode']:.6f}"
                if row["observed"]
                else "unmeasured"
            )
            lines.append(
                f"| {row['arm']} | {row['observed']}/{row['planned']} | {row['certified_successes']} | {rate} | {cost} | {row['provider_calls_total']} |"
            )
        lines.append("")
    lines += [
        "All launched stopped/error episodes remain in observed denominators. An observed rate from a partial matrix is not a completed-study rate. Solver-only and witness-copy controls are separately retained in analysis.json and are not pooled with model arms.",
        "",
        "Provider-reported known cost subtotals, unresolved reserves, missing token usage, unused generated candidates and paired common-observation counts are explicit in analysis.json. Three requested seeds are repeated executions of the same problems, not three independent datasets. Exact seeds are requested, not proof of provider determinism.",
        "",
    ]
    (args.output / "results.md").write_text("\n".join(lines))
    print(
        json.dumps(
            {
                "output": str(args.output),
                "observed": len(rows),
                "planned": report["planned"],
                "missing": len(report["missing"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
