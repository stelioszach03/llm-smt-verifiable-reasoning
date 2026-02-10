"""Utilities for validating reasoning trace payloads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence, cast

from pydantic import ValidationError as PydanticValidationError

from .types import Trace

_CONSTRAINT_KIND_TOKENS = {
    "linear_ineq",
    "int_domain",
    "bool_atom",
    "all_different",
    "and",
    "or",
    "not",
}


def validate_trace_json(data: Any) -> Trace:
    """Validate a JSON-like object against the reasoning trace models.

    Raises:
        ValidationError: If the payload does not conform to the schema.
    """

    try:
        return Trace.model_validate(data)
    except PydanticValidationError as exc:
        normalized_errors: list[Any] = []
        for error in exc.errors():
            loc = cast(
                Sequence[int | str],
                tuple(
                    part for part in error["loc"] if part not in _CONSTRAINT_KIND_TOKENS
                ),
            )
            normalized: dict[str, Any] = {
                "type": error["type"],
                "loc": loc,
                "msg": error["msg"],
            }
            if "input" in error:
                normalized["input"] = error["input"]
            if "ctx" in error:
                normalized["ctx"] = error["ctx"]
            normalized_errors.append(normalized)
        raise PydanticValidationError.from_exception_data(  # type: ignore[arg-type]
            Trace.__name__, normalized_errors
        ) from exc


def load_trace(path: Path | str) -> Trace:
    """Load and validate a reasoning trace from a JSON file."""

    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Trace file not found: {target}")
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - delegated to caller
        raise ValueError(f"Invalid JSON in {target}: {exc}") from exc

    return validate_trace_json(payload)


__all__ = ["validate_trace_json", "load_trace"]
