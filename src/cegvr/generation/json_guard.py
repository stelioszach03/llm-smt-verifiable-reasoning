"""Utilities to normalise and validate JSON-only responses."""

from __future__ import annotations

import json
import re
from typing import Any, Dict

from jsonschema import ValidationError as JsonSchemaError, validate


_CODE_FENCE_PATTERN = re.compile(r"```(?:json)?(.*?)```", re.DOTALL | re.IGNORECASE)


def strip_code_fences(payload: str) -> str:
    """Remove Markdown-style code fences from a payload."""

    match = _CODE_FENCE_PATTERN.search(payload)
    if match:
        return match.group(1).strip()
    return payload.strip()


def parse_json(payload: str) -> Any:
    """Parse a JSON string, raising ValueError with context on failure."""

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:  # pragma: no cover - passthrough for callers
        raise ValueError(
            f"Failed to parse JSON: {exc.msg} at line {exc.lineno} column {exc.colno}"
        ) from exc


def normalise_json(obj: Any) -> Any:
    """Return a deterministically ordered JSON-compatible object."""

    return json.loads(json.dumps(obj, sort_keys=True))


def validate_json(obj: Any, schema: Dict[str, Any]) -> Any:
    """Validate a JSON object against the supplied schema and normalise the result."""

    try:
        validate(instance=obj, schema=schema)
    except JsonSchemaError as exc:
        raise ValueError(f"JSON does not conform to schema: {exc.message}") from exc
    return normalise_json(obj)


def enforce_json_only(payload: str, schema: Dict[str, Any]) -> Any:
    """Strip, parse, validate, and normalise a payload expected to be JSON-only."""

    cleaned = strip_code_fences(payload)
    obj = parse_json(cleaned)
    return validate_json(obj, schema)


__all__ = [
    "strip_code_fences",
    "parse_json",
    "normalise_json",
    "validate_json",
    "enforce_json_only",
]
