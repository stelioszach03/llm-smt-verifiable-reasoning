#!/usr/bin/env python3
"""Plot recorded pilot analysis with explicit coverage; never run inference."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


NAMES = {
    "one_shot": "One shot",
    "multi_no_feedback": "No feedback",
    "multi_generic_feedback": "Generic feedback",
    "multi_unsat_core_feedback": "Conflict feedback",
    "cd_vgs_core_rank": "Core-ranked repair",
}
COLORS = ["#304a64", "#91a8b8", "#9c855e", "#64868c", "#6d667d"]
MARKERS = ["o", "s", "^", "D", "P"]


def plot_data(report):
    """Check denominator consistency before preparing plot data, without defaults."""
    if report.get("schema") != "cegvr-openrouter-pilot-analysis-v1":
        raise ValueError("Expected the recorded OpenRouter pilot analysis schema")
    groups = {}
    arms = []
    for row in report["summary"]:
        arm, stratum = row["arm"], row["stratum"]
        if stratum not in ("sat", "unsat", "all") or (arm, stratum) in groups:
            raise ValueError("Unexpected or duplicate analysis stratum")
        if arm not in arms:
            arms.append(arm)
        planned, observed, successes = (
            row["planned"],
            row["observed"],
            row["certified_successes"],
        )
        if (
            any(type(value) is not int for value in (planned, observed, successes))
            or not 0 <= successes <= observed <= planned
            or row["unlaunched_missing"] != planned - observed
        ):
            raise ValueError("Invalid observed/planned/success count")
        rate = row["observed_success_rate"]
        if observed:
            if type(rate) not in (int, float) or not math.isclose(
                rate, successes / observed, rel_tol=1e-12, abs_tol=1e-12
            ):
                raise ValueError(
                    "Observed rate does not match its explicit denominator"
                )
        elif rate is not None:
            raise ValueError("Unobserved success rate must remain null")
        cost = row["mean_accounted_cost_usd_per_observed_episode"]
        statuses = row["status_counts"]
        if (
            set(statuses) - {"complete", "stopped", "error"}
            or any(type(count) is not int or count < 0 for count in statuses.values())
            or sum(statuses.values()) != observed
        ):
            raise ValueError(
                "Recorded execution statuses do not reconcile with observed episodes"
            )
        if cost is not None and (
            type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0
        ):
            raise ValueError("Invalid accounted cost")
        if not observed and cost is not None:
            raise ValueError("Unobserved cost must remain null")
        groups[(arm, stratum)] = {
            "arm": arm,
            "name": NAMES.get(arm, arm.replace("_", " ")),
            "stratum": stratum,
            "planned": planned,
            "observed": observed,
            "successes": successes,
            "observed_unsuccessful": observed - successes,
            "unlaunched_missing": planned - observed,
            "success_percent": rate * 100 if rate is not None else None,
            "accounted_cost_usd": cost,
            "coverage_label": f"{observed}/{planned}",
            "operational_stopped": statuses.get("stopped", 0),
            "operational_errors": statuses.get("error", 0),
        }
    if not arms or any(
        (arm, stratum) not in groups
        for arm in arms
        for stratum in ("sat", "unsat", "all")
    ):
        raise ValueError("Missing declared arm/stratum summary")
    for arm in arms:
        for key in ("planned", "observed", "successes"):
            if (
                groups[(arm, "sat")][key] + groups[(arm, "unsat")][key]
                != groups[(arm, "all")][key]
            ):
                raise ValueError("SAT and UNSAT counts do not reconcile with overall")
    planned = sum(groups[(arm, "all")]["planned"] for arm in arms)
    observed = sum(groups[(arm, "all")]["observed"] for arm in arms)
    if planned != report["planned"] or observed != report["observed"]:
        raise ValueError("Arm counts do not reconcile with the overall analysis matrix")
    partial = observed != planned
    stopped = sum(groups[(arm, "all")]["operational_stopped"] for arm in arms)
    errors = sum(groups[(arm, "all")]["operational_errors"] for arm in arms)
    amendment = bool(
        report.get("post_freeze_operational_extension")
        or report.get("operational_amendment_sha256")
        or report.get("additional_admission_seconds")
    )
    disclosure = []
    if report["study_status"] != "complete":
        disclosure.append(
            f"Execution status: {report['study_status']}; matrix coverage is reported separately."
        )
    if stopped or errors:
        disclosure.append(
            f"Operational stops/errors: {stopped}/{errors}; retained as unsuccessful, not attributed to model quality."
        )
    if amendment:
        original = report.get("original_admission_seconds")
        additional = report.get("additional_admission_seconds")
        disclosure.append(
            f"Post-freeze operational extension: {original} + {additional} admission seconds; amended execution."
        )
    return {
        "arms": arms,
        "groups": groups,
        "planned": planned,
        "observed": observed,
        "partial": partial,
        "title_prefix": "PARTIAL MATRIX" if partial else "COMPLETED MATRIX",
        "coverage": f"{observed:,}/{planned:,} episodes recorded",
        "operational_stopped": stopped,
        "operational_errors": errors,
        "all_episodes_ended_normally": not partial
        and report["study_status"] == "complete"
        and not stopped
        and not errors,
        "post_freeze_operational_extension": amendment,
        "execution_disclosure": "\n".join(disclosure),
    }


def draw(analysis_path, output):
    report = json.loads(analysis_path.read_text())
    data = plot_data(report)
    if not data["observed"]:
        raise ValueError("No recorded episodes; refusing to create a results plot")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FuncFormatter, MaxNLocator

    output.mkdir(parents=True, exist_ok=False)
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titleweight": "bold",
            "axes.labelcolor": "#263a4b",
            "text.color": "#263a4b",
            "svg.fonttype": "none",
        }
    )
    paths = []

    def save(figure, name):
        for extension in ("svg", "png"):
            path = output / f"{name}.{extension}"
            figure.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
            paths.append(path)
        plt.close(figure)

    figure, axis = plt.subplots(figsize=(8.8, 6.6))
    figure.subplots_adjust(left=0.12, right=0.96, top=0.81, bottom=0.39)
    legend, costs = [], []
    for index, arm in enumerate(data["arms"]):
        row = data["groups"][(arm, "sat")]
        color, marker = COLORS[index % len(COLORS)], MARKERS[index % len(MARKERS)]
        available = (
            row["success_percent"] is not None and row["accounted_cost_usd"] is not None
        )
        if available:
            costs.append(row["accounted_cost_usd"])
            axis.scatter(
                row["accounted_cost_usd"],
                row["success_percent"],
                marker=marker,
                color=color,
                edgecolor="white",
                linewidth=0.7,
                s=90,
                zorder=3 + index,
            )
        label = f"{row['name']} - observed/planned {row['coverage_label']}"
        label += (
            f"; {row['success_percent']:.1f}%"
            if row["success_percent"] is not None
            else "; unmeasured"
        )
        if row["observed"] and row["accounted_cost_usd"] is None:
            label += "; cost unmeasured"
        legend.append(
            Line2D([], [], marker=marker, linestyle="", color=color, label=label)
        )
    axis.set(
        xlabel="Mean accounted API cost per observed SAT episode (USD)",
        ylabel="Certified SAT assignments / observed SAT episodes (%)",
        ylim=(-3, 105),
    )
    axis.set_xlim(0, max(costs) * 1.15 if costs and max(costs) else 0.0001)
    axis.xaxis.set_major_locator(MaxNLocator(5))
    axis.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"${value:.6f}"))
    axis.grid(alpha=0.17)
    axis.legend(
        handles=legend,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.24),
        frameon=False,
        fontsize=9,
    )
    figure.suptitle("SAT candidate validity versus accounted cost", fontsize=15, y=0.97)
    figure.text(
        0.5,
        0.90,
        f"{data['title_prefix']} - {data['coverage']}",
        ha="center",
        fontsize=11,
    )
    figure.text(
        0.5,
        0.015,
        "Observed denominators include stopped/error episodes. Missing cells are not zero-cost failures.\n"
        "Points are not interpolated or jittered; overlaps remain visible in the legend. No CIs or significance claims."
        + ("\n" + data["execution_disclosure"] if data["execution_disclosure"] else ""),
        ha="center",
        fontsize=8.5,
    )
    save(figure, "sat-success-versus-cost")

    figure, axes = plt.subplots(1, 2, figsize=(12.4, 6.0))
    figure.subplots_adjust(left=0.17, right=0.97, top=0.77, bottom=0.25, wspace=0.62)
    for axis, stratum, heading in zip(
        axes,
        ("sat", "unsat"),
        ("SAT: complete valid assignments", "UNSAT: solver-confirmed claims"),
        strict=True,
    ):
        rows = [data["groups"][(arm, stratum)] for arm in data["arms"]]
        for index, row in enumerate(rows):
            left = 0
            for key, color, label in (
                ("successes", "#648b86", "Certified"),
                ("observed_unsuccessful", "#b39a7a", "Observed, uncertified"),
                ("unlaunched_missing", "#e1e6e9", "Missing / unlaunched"),
            ):
                value = row[key]
                axis.barh(
                    index,
                    value,
                    left=left,
                    color=color,
                    edgecolor="white",
                    height=0.62,
                    label=label if index == 0 else None,
                )
                if value:
                    axis.text(
                        left + value / 2,
                        index,
                        str(value),
                        ha="center",
                        va="center",
                        fontsize=9,
                    )
                left += value
        axis.set(
            yticks=range(len(rows)),
            yticklabels=[
                f"{row['name']}\nobserved/planned {row['coverage_label']}"
                for row in rows
            ],
            xlabel="Prespecified eligible episodes",
            title=heading,
            xlim=(0, max(row["planned"] for row in rows) or 1),
        )
        axis.invert_yaxis()
        axis.xaxis.set_major_locator(MaxNLocator(integer=True))
        axis.tick_params(axis="y", length=0)
    figure.suptitle("Formal certification and matrix coverage", fontsize=15, y=0.97)
    figure.text(
        0.5,
        0.90,
        f"{data['title_prefix']} - {data['coverage']}",
        ha="center",
        fontsize=11,
    )
    handles, labels = axes[0].get_legend_handles_labels()
    figure.legend(
        handles,
        labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.12),
        ncol=3,
        frameon=False,
    )
    figure.text(
        0.5,
        0.01,
        "SAT and UNSAT use separate eligible denominators. A Z3-certified UNSAT claim is not an LLM-produced proof.\n"
        "Three requested seeds repeat the same problems; this is a descriptive pilot, not three independent datasets."
        + ("\n" + data["execution_disclosure"] if data["execution_disclosure"] else ""),
        ha="center",
        fontsize=8.5,
    )
    save(figure, "sat-unsat-certification-counts")
    provenance = {
        "analysis_sha256": hashlib.sha256(analysis_path.read_bytes()).hexdigest(),
        "plot_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "matplotlib_version": matplotlib.__version__,
        "observed": data["observed"],
        "planned": data["planned"],
        "partial_matrix": data["partial"],
        "operational_stopped": data["operational_stopped"],
        "operational_errors": data["operational_errors"],
        "all_episodes_ended_normally": data["all_episodes_ended_normally"],
        "post_freeze_operational_extension": data["post_freeze_operational_extension"],
        "operational_amendment_sha256": report.get("operational_amendment_sha256"),
        "published_amendment_reference": report.get("published_amendment_reference"),
        "confidence_intervals": None,
        "significance_claim": False,
        "figures": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
        },
    }
    (output / "figure-provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n"
    )
    return paths


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "analysis", type=Path, help="Recorded analysis.json, never a provider endpoint"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="New standalone figure directory"
    )
    args = parser.parse_args(argv)
    for path in draw(args.analysis, args.output):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
