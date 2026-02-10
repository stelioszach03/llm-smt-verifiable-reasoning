"""High-level interface for checking reasoning traces with Z3."""

from __future__ import annotations

from time import perf_counter
from typing import Any, Dict

import z3

from cegvr.grammar.types import Trace

from .encoder import build_z3_context, encode_constraints, extract_model


def check_trace(trace: Trace, timeout_ms: int = 2000) -> Dict[str, Any]:
    """Check satisfiability of a reasoning trace using Z3."""

    solver, varmap = build_z3_context(trace)
    encode_constraints(solver, varmap, trace.constraints)
    solver.set("timeout", timeout_ms)

    start = perf_counter()
    result = solver.check()
    elapsed_ms = (perf_counter() - start) * 1000

    payload: Dict[str, Any] = {"time_ms": elapsed_ms}

    if result == z3.sat:
        payload["status"] = "sat"
        payload["model"] = extract_model(solver, varmap)
        return payload

    if result == z3.unsat:
        payload["status"] = "unsat"
        labels = [str(item) for item in solver.unsat_core()]
        payload["unsat_core"] = labels
        # Attach human-readable descriptions when available
        context = getattr(solver, "_cegvr_context", None)
        if context is not None and getattr(context, "labels", None):
            desc_map = {lab: context.labels.get(lab, "") for lab in labels}
            payload["unsat_descriptions"] = [
                desc for _, desc in desc_map.items() if desc
            ]
        return payload

    reason = solver.reason_unknown()
    if reason == "timeout":
        payload["status"] = "timeout"
    else:
        payload["status"] = "unknown"
        if reason:
            payload["reason"] = reason
    return payload


__all__ = ["check_trace"]
