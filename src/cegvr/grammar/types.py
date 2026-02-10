"""Typed models mirroring the reasoning trace JSON schema."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Bounds(BaseModel):
    """Closed interval bounds for integer variables."""

    lower: int | None = None
    upper: int | None = None

    @model_validator(mode="after")
    def validate_interval(self) -> "Bounds":
        """Ensure at least one bound is present and the interval is consistent."""

        if self.lower is None and self.upper is None:
            raise ValueError("at least one of lower or upper must be provided")
        return self


class Variable(BaseModel):
    """Problem variable declaration."""

    name: str
    domain: Literal["int", "bool"]
    bounds: Bounds | None = None

    @model_validator(mode="after")
    def ensure_bounds_valid(self) -> "Variable":
        """Disallow bounds for boolean variables."""

        if self.domain == "bool" and self.bounds is not None:
            raise ValueError("boolean variables cannot specify bounds")
        return self


class ConstantExpr(BaseModel):
    """Literal constant expression."""

    type: Literal["constant"]
    value: int | float | bool | str


class VariableExpr(BaseModel):
    """Variable reference expression."""

    type: Literal["variable"]
    name: str


class UnaryExpr(BaseModel):
    """Unary operator expression."""

    type: Literal["unary"]
    op: Literal["-", "not"]
    operand: "Expression"


class BinaryExpr(BaseModel):
    """Binary operator expression."""

    type: Literal["binary"]
    op: Literal[
        "+",
        "-",
        "*",
        "/",
        "and",
        "or",
        "=",
        "!=",
        "<",
        "<=",
        ">",
        ">=",
        "=>",
    ]
    left: "Expression"
    right: "Expression"


class FunctionExpr(BaseModel):
    """N-ary function call expression."""

    type: Literal["function"]
    name: str
    args: list["Expression"] = Field(default_factory=list)


Expression = Annotated[
    ConstantExpr | VariableExpr | UnaryExpr | BinaryExpr | FunctionExpr,
    Field(discriminator="type"),
]


class LinearTerm(BaseModel):
    """Single term in a linear inequality."""

    variable: str
    coefficient: float = 1.0


class LinearIneqConstraint(BaseModel):
    """Linear inequality of the form sum(coeff_i * var_i) + offset relation rhs."""

    kind: Literal["linear_ineq"]
    terms: list[LinearTerm]
    relation: Literal["<=", ">=", "="]
    rhs: float
    offset: float = 0.0

    @field_validator("terms")
    @classmethod
    def ensure_terms_present(cls, value: list[LinearTerm]) -> list[LinearTerm]:
        if not value:
            raise ValueError("linear inequalities require at least one term")
        return value


class IntDomainConstraint(BaseModel):
    """Integral domain bounds for a variable."""

    kind: Literal["int_domain"]
    variable: str
    lower: int
    upper: int

    @model_validator(mode="after")
    def ensure_bounds(self) -> "IntDomainConstraint":
        return self


class BoolAtomConstraint(BaseModel):
    """Boolean assignment constraint."""

    kind: Literal["bool_atom"]
    variable: str
    value: bool


class AllDifferentConstraint(BaseModel):
    """All-different constraint across a set of variables."""

    kind: Literal["all_different"]
    variables: list[str]

    @field_validator("variables")
    @classmethod
    def ensure_multiple(cls, value: list[str]) -> list[str]:
        unique = set(value)
        if len(value) < 2:
            raise ValueError("all_different requires at least two variables")
        if len(unique) != len(value):
            raise ValueError("variable names in all_different must be unique")
        return value


class AndConstraint(BaseModel):
    """Logical conjunction constraint."""

    kind: Literal["and"]
    constraints: list["Constraint"]

    @field_validator("constraints")
    @classmethod
    def ensure_minimum(cls, value: list["Constraint"]) -> list["Constraint"]:
        if len(value) < 2:
            raise ValueError("and constraints require at least two operands")
        return value


class OrConstraint(BaseModel):
    """Logical disjunction constraint."""

    kind: Literal["or"]
    constraints: list["Constraint"]

    @field_validator("constraints")
    @classmethod
    def ensure_minimum(cls, value: list["Constraint"]) -> list["Constraint"]:
        if len(value) < 2:
            raise ValueError("or constraints require at least two operands")
        return value


class NotConstraint(BaseModel):
    """Logical negation constraint."""

    kind: Literal["not"]
    constraint: "Constraint"


Constraint = Annotated[
    LinearIneqConstraint
    | IntDomainConstraint
    | BoolAtomConstraint
    | AllDifferentConstraint
    | AndConstraint
    | OrConstraint
    | NotConstraint,
    Field(discriminator="kind"),
]


class Step(BaseModel):
    """Single reasoning step."""

    id: int = Field(ge=0)
    kind: Literal["derive", "assume", "case"]
    expr: Expression
    note: str | None = None


class Objective(BaseModel):
    """Objective definition for the trace."""

    type: Literal["value", "minimize", "maximize"]
    target: Expression | None = None


class Answer(BaseModel):
    """Final answer payload."""

    value: Any
    justification: str


class Trace(BaseModel):
    """Root reasoning trace object."""

    problem_id: str
    task: Literal["math", "scheduling", "planning"]
    variables: list[Variable]
    assumptions: list[str] = Field(default_factory=list)
    steps: list[Step]
    constraints: list[Constraint]
    objective: Objective | None = None
    answer: Answer | None = None

    @model_validator(mode="after")
    def ensure_unique_variables(self) -> "Trace":
        names = [var.name for var in self.variables]
        if len(set(names)) != len(names):
            raise ValueError("variable names must be unique")
        return self


# Resolve recursive type references for Pydantic.
UnaryExpr.model_rebuild()
BinaryExpr.model_rebuild()
FunctionExpr.model_rebuild()
AndConstraint.model_rebuild()
OrConstraint.model_rebuild()
NotConstraint.model_rebuild()
Step.model_rebuild()
Objective.model_rebuild()
Trace.model_rebuild()

__all__ = [
    "Answer",
    "AndConstraint",
    "BoolAtomConstraint",
    "Bounds",
    "Constraint",
    "FunctionExpr",
    "LinearIneqConstraint",
    "LinearTerm",
    "NotConstraint",
    "Objective",
    "OrConstraint",
    "Step",
    "Trace",
    "UnaryExpr",
    "BinaryExpr",
    "Variable",
    "Expression",
    "ConstantExpr",
    "VariableExpr",
    "AllDifferentConstraint",
    "IntDomainConstraint",
]
