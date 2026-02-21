"""Typed contracts for the candidate-first paper pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExperimentArm(str, Enum):
    """Paper-study arm identifiers."""

    ONE_SHOT = "one_shot"
    MULTI_NO_FEEDBACK = "multi_no_feedback"
    MULTI_GENERIC_FEEDBACK = "multi_generic_feedback"
    MULTI_UNSAT_CORE_FEEDBACK = "multi_unsat_core_feedback"
    CD_VGS_CORE_RANK = "cd_vgs_core_rank"

    @property
    def is_multi_round(self) -> bool:
        return self is not ExperimentArm.ONE_SHOT

    @property
    def is_compute_matched(self) -> bool:
        return self is not ExperimentArm.ONE_SHOT


class ConstraintReference(BaseModel):
    """Human-readable tracked constraint reference."""

    constraint_id: str
    constraint_text: str


class CandidateOutput(BaseModel):
    """LLM output contract for the candidate-first linear pipeline."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["sat", "unsat"]
    assignment: dict[str, int | bool] | None = None
    unsat_explanation: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "CandidateOutput":
        if self.status == "sat":
            if not self.assignment:
                raise ValueError("sat candidates must include a non-empty assignment")
        elif self.assignment is not None:
            raise ValueError("unsat candidates must not include an assignment")
        return self


def candidate_output_schema() -> dict[str, Any]:
    """Return a JSON Schema for candidate-side generation."""

    return {
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
        "allOf": [
            {
                "if": {
                    "properties": {"status": {"const": "sat"}},
                    "required": ["status"],
                },
                "then": {"required": ["assignment"]},
            },
            {
                "if": {
                    "properties": {"status": {"const": "unsat"}},
                    "required": ["status"],
                },
                "then": {
                    "not": {"required": ["assignment"]},
                },
            },
        ],
    }


@dataclass(slots=True)
class CandidateProposal:
    """Parsed LLM proposal with attached generation metadata."""

    candidate: CandidateOutput | None
    raw_content: str | None
    raw_payload: dict[str, Any] | None
    llm_latency_ms: float = 0.0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class VerifierFeedback(BaseModel):
    """Round-level feedback object carried between attempts."""

    model_config = ConfigDict(extra="forbid")

    round_index: int
    failure_type: str
    verifier_result: str
    generic_feedback: str | None = None
    unsat_core: list[ConstraintReference] = Field(default_factory=list)
    sat_witness: dict[str, int | bool] | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    variables_to_revise: list[str] = Field(default_factory=list)
    variables_to_keep_fixed: list[str] = Field(default_factory=list)
    core_variables: list[str] = Field(default_factory=list)
    conflict_constraints: list[ConstraintReference] = Field(default_factory=list)
    repeat_failure_count: int = 0
    search_score: tuple[int, ...] | None = None


class CandidateVerification(BaseModel):
    """Verifier outcome for a single candidate."""

    model_config = ConfigDict(extra="forbid")

    predicted_status: Literal["sat", "unsat"] | None = None
    verified_outcome: str
    verifier_result: str
    failure_type: str | None = None
    solver_time_ms: float = 0.0
    unsat_core: list[ConstraintReference] = Field(default_factory=list)
    sat_witness: dict[str, int | bool] | None = None
    certified_assignment: dict[str, int | bool] | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    precheck_violations: int = 0


class AttemptRecord(BaseModel):
    """Serialized attempt record for run logs and ranking."""

    model_config = ConfigDict(extra="allow")

    round_index: int
    candidate_index: int
    predicted_status: Literal["sat", "unsat"] | None = None
    verified_outcome: str
    verifier_result: str
    failure_type: str | None = None
    precheck_violations: int = 0
    unsat_core_size: int = 0
    llm_latency_ms: float = 0.0
    solver_latency_ms: float = 0.0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    feedback_source_score: tuple[int, int, int] | None = None
    search_score: tuple[int, ...] | None = None
    failure_signature: tuple[str, ...] | None = None
    repeat_failure_count: int = 0
    violated_constraint_ids: list[str] = Field(default_factory=list)
    conflict_constraints: list[ConstraintReference] = Field(default_factory=list)
    core_variables: list[str] = Field(default_factory=list)
    variables_to_revise: list[str] = Field(default_factory=list)
    variables_to_keep_fixed: list[str] = Field(default_factory=list)
