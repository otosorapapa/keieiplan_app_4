"""Validation helpers for user supplied financial inputs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple

from pydantic import ValidationError

from models import (
    CapexPlan,
    CostPlan,
    FinanceBundle,
    LoanSchedule,
    SalesPlan,
    TaxPolicy,
)


@dataclass(frozen=True)
class ValidationIssue:
    """Represents a validation error for a specific field."""

    field: str
    message: str


def _issues_from_error(prefix: str, error: ValidationError) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    for detail in error.errors():
        path = ".".join(str(part) for part in detail.get("loc", ()))
        message = detail.get("msg", "不正な値です。")
        field = f"{prefix}.{path}" if prefix and path else prefix or path
        issues.append(ValidationIssue(field=field, message=message))
    return issues


def validate_sales(data: Dict[str, Any]) -> Tuple[SalesPlan | None, List[ValidationIssue]]:
    try:
        plan = SalesPlan(**data)
        return plan, []
    except ValidationError as exc:
        return None, _issues_from_error("sales", exc)


def validate_costs(data: Dict[str, Any]) -> Tuple[CostPlan | None, List[ValidationIssue]]:
    try:
        plan = CostPlan(**data)
        return plan, []
    except ValidationError as exc:
        return None, _issues_from_error("costs", exc)


def validate_capex(data: Dict[str, Any]) -> Tuple[CapexPlan | None, List[ValidationIssue]]:
    try:
        plan = CapexPlan(**data)
        return plan, []
    except ValidationError as exc:
        return None, _issues_from_error("capex", exc)


def validate_loans(data: Dict[str, Any]) -> Tuple[LoanSchedule | None, List[ValidationIssue]]:
    try:
        schedule = LoanSchedule(**data)
        return schedule, []
    except ValidationError as exc:
        return None, _issues_from_error("loans", exc)


def validate_tax(data: Dict[str, Any]) -> Tuple[TaxPolicy | None, List[ValidationIssue]]:
    try:
        policy = TaxPolicy(**data)
        return policy, []
    except ValidationError as exc:
        return None, _issues_from_error("tax", exc)


def validate_bundle(data: Dict[str, Any]) -> Tuple[FinanceBundle | None, List[ValidationIssue]]:
    """Validate a nested dictionary covering all plan components."""

    sales, sales_errs = validate_sales(data.get("sales", {}))
    costs, cost_errs = validate_costs(data.get("costs", {}))
    capex, capex_errs = validate_capex(data.get("capex", {}))
    loans, loan_errs = validate_loans(data.get("loans", {}))
    tax, tax_errs = validate_tax(data.get("tax", {}))

    issues: List[ValidationIssue] = []
    issues.extend(sales_errs)
    issues.extend(cost_errs)
    issues.extend(capex_errs)
    issues.extend(loan_errs)
    issues.extend(tax_errs)

    if issues:
        return None, issues

    assert sales and costs and capex and loans and tax  # for mypy/static typing
    bundle = FinanceBundle(sales=sales, costs=costs, capex=capex, loans=loans, tax=tax)
    return bundle, []


def collect_error_messages(issues: Iterable[ValidationIssue]) -> str:
    return "\n".join(f"[{issue.field}] {issue.message}" for issue in issues)


__all__ = [
    "ValidationIssue",
    "validate_sales",
    "validate_costs",
    "validate_capex",
    "validate_loans",
    "validate_tax",
    "validate_bundle",
    "collect_error_messages",
]
