"""Structured error taxonomy for the CEGVR engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(slots=True)
class CEGVRError(Exception):
    """Base class for engine errors."""

    message: str
    context: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "type": self.__class__.__name__,
            "message": self.message,
        }
        if self.context:
            payload["context"] = self.context  # type: ignore[assignment]
        return payload


class ValidationError(CEGVRError):
    """Raised when inputs fail schema or type validation."""


class TranslationError(CEGVRError):
    """Raised when translating traces or problems into solver form fails."""


class SolverTimeout(CEGVRError):
    """Raised when the SMT solver exceeds the configured timeout."""


class SolverUnknown(CEGVRError):
    """Raised when the SMT solver returns unknown without timeout."""


class NoCoverage(CEGVRError):
    """Raised when no viable candidates are produced across repair rounds."""


class GenerationError(CEGVRError):
    """Raised when the generator fails to produce candidates."""


__all__ = [
    "CEGVRError",
    "ValidationError",
    "TranslationError",
    "SolverTimeout",
    "SolverUnknown",
    "NoCoverage",
    "GenerationError",
]
