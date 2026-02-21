"""Translation utilities from reasoning traces to Z3 constraints."""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Dict, Sequence

import z3

from cegvr.grammar.types import (
    AllDifferentConstraint,
    BoolAtomConstraint,
    Constraint,
    IntDomainConstraint,
    LinearIneqConstraint,
    NotConstraint,
    OrConstraint,
    Trace,
    LinearTerm,
    AndConstraint,
)


@dataclass
class SolverContext:
    """Internal helper to track assertion labels for unsat core reporting."""

    solver: z3.Solver
    next_index: int = 0
    labels: dict[str, str] = field(default_factory=dict)

    def track(
        self,
        expr: z3.BoolRef,
        prefix: str,
        desc: str | None = None,
        label: str | None = None,
    ) -> None:
        """Assert an expression with a generated tracking literal and optional description."""

        tracking_label = label or f"{prefix}:{self.next_index}"
        self.next_index += 1
        self.solver.assert_and_track(expr, tracking_label)
        if desc:
            self.labels[tracking_label] = desc


def build_z3_context(trace: Trace) -> tuple[z3.Solver, dict[str, z3.ExprRef]]:
    """Create a Z3 solver and variable map for the provided trace."""

    solver = z3.Solver()
    solver.set(unsat_core=True)
    context = SolverContext(solver=solver)

    varmap: Dict[str, z3.ExprRef] = {}

    for variable in trace.variables:
        if variable.domain == "int":
            symbol: z3.ExprRef = z3.Int(variable.name)
            varmap[variable.name] = symbol
            if variable.bounds is not None:
                if variable.bounds.lower is not None:
                    context.track(
                        symbol >= variable.bounds.lower,
                        f"domain:{variable.name}:lower",
                        desc=f"{variable.name} >= {variable.bounds.lower}",
                    )
                if variable.bounds.upper is not None:
                    context.track(
                        symbol <= variable.bounds.upper,
                        f"domain:{variable.name}:upper",
                        desc=f"{variable.name} <= {variable.bounds.upper}",
                    )
        else:
            symbol = z3.Bool(variable.name)
            varmap[variable.name] = symbol

    # Store context on solver for reuse in encoding stage.
    solver._cegvr_context = context  # type: ignore[attr-defined]
    return solver, varmap


def _get_context(solver: z3.Solver) -> SolverContext:
    context = getattr(solver, "_cegvr_context", None)
    if context is None:
        context = SolverContext(solver=solver)
        solver._cegvr_context = context  # type: ignore[attr-defined]
    return context


def encode_constraints(
    solver: z3.Solver,
    varmap: Dict[str, z3.ExprRef],
    constraints: Sequence[Constraint],
) -> None:
    """Encode the provided constraints into the solver."""

    context = _get_context(solver)
    for constraint in constraints:
        expr = encode_constraint_expr(constraint, varmap)
        desc = describe_constraint(constraint)
        context.track(expr, "constraint", desc=desc)


def encode_constraint_expr(
    constraint: Constraint, varmap: Dict[str, z3.ExprRef]
) -> z3.BoolRef:
    if isinstance(constraint, LinearIneqConstraint):
        return _encode_linear(constraint, varmap)
    if isinstance(constraint, IntDomainConstraint):
        symbol = _require_variable(varmap, constraint.variable)
        return z3.And(symbol >= constraint.lower, symbol <= constraint.upper)
    if isinstance(constraint, BoolAtomConstraint):
        symbol = _require_variable(varmap, constraint.variable)
        return symbol == constraint.value
    if isinstance(constraint, AllDifferentConstraint):
        symbols = [_require_variable(varmap, name) for name in constraint.variables]
        return z3.Distinct(*symbols)
    if isinstance(constraint, AndConstraint):
        return z3.And(
            *(encode_constraint_expr(child, varmap) for child in constraint.constraints)
        )
    if isinstance(constraint, OrConstraint):
        return z3.Or(
            *(encode_constraint_expr(child, varmap) for child in constraint.constraints)
        )
    if isinstance(constraint, NotConstraint):
        return z3.Not(encode_constraint_expr(constraint.constraint, varmap))
    raise TypeError(f"Unsupported constraint kind: {constraint}")


def describe_constraint(constraint: Constraint) -> str:
    """Produce a human-readable description of a constraint for feedback."""
    if isinstance(constraint, LinearIneqConstraint):
        parts: list[str] = []
        for term in constraint.terms:
            coeff = term.coefficient
            var = term.variable
            parts.append(f"({coeff})*{var}")
        lhs = " + ".join(parts) if parts else "0"
        if getattr(constraint, "offset", 0):
            lhs = f"{lhs} + {constraint.offset}"
        return f"{lhs} {constraint.relation} {constraint.rhs}"
    if isinstance(constraint, IntDomainConstraint):
        return f"{constraint.lower} <= {constraint.variable} <= {constraint.upper}"
    if isinstance(constraint, BoolAtomConstraint):
        return f"{constraint.variable} == {constraint.value}"
    if isinstance(constraint, AllDifferentConstraint):
        return "all_different(" + ", ".join(constraint.variables) + ")"
    if isinstance(constraint, AndConstraint):
        return (
            "AND["
            + "; ".join(describe_constraint(c) for c in constraint.constraints)
            + "]"
        )
    if isinstance(constraint, OrConstraint):
        return (
            "OR["
            + "; ".join(describe_constraint(c) for c in constraint.constraints)
            + "]"
        )
    if isinstance(constraint, NotConstraint):
        return "NOT(" + describe_constraint(constraint.constraint) + ")"
    return repr(constraint)


def _encode_linear(
    constraint: LinearIneqConstraint, varmap: Dict[str, z3.ExprRef]
) -> z3.BoolRef:
    terms = [_encode_linear_term(term, varmap) for term in constraint.terms]
    offset = z3.RealVal(constraint.offset)
    if terms:
        total = z3.Sum(*terms, offset)
    else:
        total = offset
    rhs = z3.RealVal(constraint.rhs)

    if constraint.relation == "<=":
        return total <= rhs
    if constraint.relation == ">=":
        return total >= rhs
    if constraint.relation == "=":
        return total == rhs
    raise ValueError(f"Unknown linear relation: {constraint.relation}")


def _encode_linear_term(term: LinearTerm, varmap: Dict[str, z3.ExprRef]) -> z3.ArithRef:
    symbol = _require_variable(varmap, term.variable)
    coeff = z3.RealVal(term.coefficient)
    if z3.is_bool(symbol):
        symbol_real = z3.If(symbol, z3.RealVal(1), z3.RealVal(0))
    else:
        symbol_real = z3.ToReal(symbol)
    return coeff * symbol_real


def _require_variable(varmap: Dict[str, z3.ExprRef], name: str) -> z3.ExprRef:
    if name not in varmap:
        raise KeyError(f"Variable '{name}' referenced before declaration")
    return varmap[name]


def extract_model(
    solver: z3.Solver, varmap: Dict[str, z3.ExprRef]
) -> Dict[str, int | bool]:
    """Extract a model mapping from a satisfiable solver state."""

    model = solver.model()
    result: Dict[str, int | bool] = {}
    for name, symbol in varmap.items():
        value = model.eval(symbol, model_completion=True)
        if z3.is_true(value):
            result[name] = True
        elif z3.is_false(value):
            result[name] = False
        elif z3.is_int_value(value):
            result[name] = value.as_long()
        elif z3.is_rational_value(value):
            fraction: Fraction = value.as_fraction()
            if fraction.denominator != 1:
                raise ValueError(
                    f"Non-integer rational value encountered for variable '{name}': {fraction}"
                )
            result[name] = fraction.numerator
    return result
