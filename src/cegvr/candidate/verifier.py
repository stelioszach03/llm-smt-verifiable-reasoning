"""Verifier for candidate-first linear-style assignments."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from pydantic import TypeAdapter, ValidationError as PydanticValidationError
import z3

from cegvr.grammar.types import Constraint
from cegvr.smt.encoder import SolverContext, describe_constraint, encode_constraint_expr
from cegvr.smt.encoder import extract_model as extract_solver_model

from .types import CandidateOutput, CandidateVerification, ConstraintReference

_CONSTRAINT_ADAPTER = TypeAdapter(Constraint)


def verify_linear_candidate(
    problem: dict,
    candidate: CandidateOutput,
    *,
    timeout_ms: int = 2000,
) -> CandidateVerification:
    """Verify a candidate assignment or UNSAT claim against the problem."""

    predicted_status = candidate.status
    variables = problem.get("variables", [])
    constraints = _load_constraints(problem)

    if predicted_status == "sat":
        assignment = dict(candidate.assignment or {})
        precheck = _precheck_assignment(variables, assignment)
        if precheck:
            return CandidateVerification(
                predicted_status=predicted_status,
                verified_outcome="REJECTED_DOMAIN",
                verifier_result="precheck",
                failure_type="domain_violation",
                diagnostics={
                    "last_assignment": assignment,
                    "precheck_errors": precheck,
                    "violated_constraint_ids": [],
                    "violated_constraint_texts": [],
                },
                precheck_violations=len(precheck),
            )

        # Only evaluate expressions once every referenced variable has a complete,
        # correctly typed in-domain assignment. Missing/malformed values are
        # rejected candidates, not exceptions that abort the evaluation study.
        violations = _count_constraint_violations(constraints, assignment)
        precheck_violations = len(violations)

        solver, context, varmap = _build_problem_solver(
            problem, constraints, timeout_ms
        )
        for spec in variables:
            name = spec["name"]
            expr = _assignment_expr(varmap[name], assignment[name])
            context.track(
                expr,
                "assignment",
                desc=f"{name} == {assignment[name]}",
                label=f"a:{name}",
            )

        start = perf_counter()
        result = solver.check()
        solver_time_ms = (perf_counter() - start) * 1000.0
        if result == z3.sat:
            return CandidateVerification(
                predicted_status=predicted_status,
                verified_outcome="CERTIFIED_SAT",
                verifier_result="sat",
                solver_time_ms=solver_time_ms,
                certified_assignment=assignment,
                diagnostics={
                    "violated_constraint_ids": [
                        ref.constraint_id for ref in violations
                    ],
                },
                precheck_violations=precheck_violations,
            )
        if result == z3.unsat:
            core = _extract_problem_core(solver, context)
            return CandidateVerification(
                predicted_status=predicted_status,
                verified_outcome="FAILED_CERTIFICATION",
                verifier_result="unsat",
                failure_type="constraint_violation",
                solver_time_ms=solver_time_ms,
                unsat_core=core,
                diagnostics={
                    "violated_constraint_ids": [
                        ref.constraint_id for ref in violations
                    ],
                    "violated_constraint_texts": [
                        ref.constraint_text for ref in violations
                    ],
                    "last_assignment": assignment,
                },
                precheck_violations=precheck_violations,
            )
        reason = solver.reason_unknown()
        return CandidateVerification(
            predicted_status=predicted_status,
            verified_outcome=(
                "VERIFIER_TIMEOUT" if reason == "timeout" else "VERIFIER_UNKNOWN"
            ),
            verifier_result="timeout" if reason == "timeout" else "unknown",
            failure_type="verifier_timeout"
            if reason == "timeout"
            else "verifier_unknown",
            solver_time_ms=solver_time_ms,
            diagnostics={"reason": reason or None, "last_assignment": assignment},
            precheck_violations=precheck_violations,
        )

    solver, context, varmap = _build_problem_solver(problem, constraints, timeout_ms)
    start = perf_counter()
    result = solver.check()
    solver_time_ms = (perf_counter() - start) * 1000.0
    if result == z3.unsat:
        return CandidateVerification(
            predicted_status=predicted_status,
            verified_outcome="CERTIFIED_UNSAT",
            verifier_result="unsat",
            solver_time_ms=solver_time_ms,
            unsat_core=_extract_problem_core(solver, context),
        )
    if result == z3.sat:
        return CandidateVerification(
            predicted_status=predicted_status,
            verified_outcome="FALSE_UNSAT_CLAIM",
            verifier_result="sat",
            failure_type="false_unsat_claim",
            solver_time_ms=solver_time_ms,
            sat_witness=extract_solver_model(solver, varmap),
        )
    reason = solver.reason_unknown()
    return CandidateVerification(
        predicted_status=predicted_status,
        verified_outcome=(
            "VERIFIER_TIMEOUT" if reason == "timeout" else "VERIFIER_UNKNOWN"
        ),
        verifier_result="timeout" if reason == "timeout" else "unknown",
        failure_type="verifier_timeout" if reason == "timeout" else "verifier_unknown",
        solver_time_ms=solver_time_ms,
        diagnostics={"reason": reason or None},
    )


def _build_problem_solver(
    problem: dict, constraints: list[tuple[str, Constraint]], timeout_ms: int
) -> tuple[z3.Solver, SolverContext, dict[str, z3.ExprRef]]:
    solver = z3.Solver()
    solver.set(unsat_core=True)
    solver.set(timeout=timeout_ms)
    context = SolverContext(solver=solver)
    varmap: dict[str, z3.ExprRef] = {}

    for spec in problem.get("variables", []):
        name = spec["name"]
        domain = spec.get("domain", "int")
        bounds = spec.get("bounds") or {}
        if domain == "bool":
            symbol: z3.ExprRef = z3.Bool(name)
        else:
            symbol = z3.Int(name)
        varmap[name] = symbol

        if domain != "bool" and bounds.get("lower") is not None:
            context.track(
                symbol >= int(bounds["lower"]),
                "domain",
                desc=f"{name} >= {bounds['lower']}",
                label=f"d:{name}:lower",
            )
        if domain != "bool" and bounds.get("upper") is not None:
            context.track(
                symbol <= int(bounds["upper"]),
                "domain",
                desc=f"{name} <= {bounds['upper']}",
                label=f"d:{name}:upper",
            )

    for constraint_id, constraint in constraints:
        context.track(
            encode_constraint_expr(constraint, varmap),
            "constraint",
            desc=describe_constraint(constraint),
            label=constraint_id,
        )

    return solver, context, varmap


def _load_constraints(problem: dict) -> list[tuple[str, Constraint]]:
    parsed: list[tuple[str, Constraint]] = []
    for index, raw in enumerate(problem.get("constraints", []), start=1):
        constraint_id = str(raw.get("constraint_id") or f"c{index}")
        try:
            parsed.append((constraint_id, _CONSTRAINT_ADAPTER.validate_python(raw)))
        except PydanticValidationError as exc:
            raise ValueError(f"Invalid constraint {constraint_id}: {exc}") from exc
    return parsed


def _precheck_assignment(
    variables: list[dict], assignment: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    expected = {spec["name"]: spec for spec in variables}
    for name in assignment:
        if name not in expected:
            errors.append(f"unexpected variable '{name}'")
    for name, spec in expected.items():
        if name not in assignment:
            errors.append(f"missing variable '{name}'")
            continue
        value = assignment[name]
        domain = spec.get("domain", "int")
        bounds = spec.get("bounds") or {}
        if domain == "bool":
            if not isinstance(value, bool):
                errors.append(f"variable '{name}' must be boolean")
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append(f"variable '{name}' must be integer")
            continue
        lower = bounds.get("lower")
        upper = bounds.get("upper")
        if lower is not None and value < int(lower):
            errors.append(f"variable '{name}' below lower bound")
        if upper is not None and value > int(upper):
            errors.append(f"variable '{name}' above upper bound")
    return errors


def _count_constraint_violations(
    constraints: list[tuple[str, Constraint]], assignment: dict[str, Any]
) -> list[ConstraintReference]:
    violated: list[ConstraintReference] = []
    for constraint_id, constraint in constraints:
        if not _evaluate_constraint(constraint, assignment):
            violated.append(
                ConstraintReference(
                    constraint_id=constraint_id,
                    constraint_text=describe_constraint(constraint),
                )
            )
    return violated


def _evaluate_constraint(constraint: Constraint, assignment: dict[str, Any]) -> bool:
    kind = constraint.kind
    if kind == "linear_ineq":
        lhs = float(constraint.offset)
        for term in constraint.terms:
            lhs += float(term.coefficient) * float(assignment[term.variable])
        rhs = float(constraint.rhs)
        if constraint.relation == "<=":
            return lhs <= rhs
        if constraint.relation == ">=":
            return lhs >= rhs
        return lhs == rhs
    if kind == "int_domain":
        value = int(assignment[constraint.variable])
        return int(constraint.lower) <= value <= int(constraint.upper)
    if kind == "bool_atom":
        return bool(assignment[constraint.variable]) == bool(constraint.value)
    if kind == "all_different":
        values = [assignment[name] for name in constraint.variables]
        return len(values) == len(set(values))
    if kind == "and":
        return all(
            _evaluate_constraint(child, assignment) for child in constraint.constraints
        )
    if kind == "or":
        return any(
            _evaluate_constraint(child, assignment) for child in constraint.constraints
        )
    if kind == "not":
        return not _evaluate_constraint(constraint.constraint, assignment)
    raise TypeError(f"Unsupported constraint kind: {kind}")


def _assignment_expr(symbol: z3.ExprRef, value: int | bool) -> z3.BoolRef:
    if z3.is_bool(symbol):
        return symbol == bool(value)
    return symbol == int(value)


def _extract_problem_core(
    solver: z3.Solver, context: SolverContext
) -> list[ConstraintReference]:
    refs: list[ConstraintReference] = []
    for item in solver.unsat_core():
        label = str(item)
        if not label.startswith("c"):
            continue
        refs.append(
            ConstraintReference(
                constraint_id=label,
                constraint_text=context.labels.get(label, label),
            )
        )
    return refs
