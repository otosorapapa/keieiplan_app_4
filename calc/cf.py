"""Cash flow estimation utilities."""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Tuple

from models import CapexPlan, LoanPayment, LoanSchedule, TaxPolicy

DEFAULT_DISCOUNT_RATE = Decimal("0.05")
DEFAULT_PROJECTION_MONTHS = 120


def _capex_first_year_total(capex: CapexPlan) -> Decimal:
    return sum(
        (entry.amount for entry in capex.payment_schedule() if entry.year == 1),
        start=Decimal("0"),
    )


def _principal_first_year_total(loans: LoanSchedule) -> Decimal:
    return sum(
        (entry.principal for entry in loans.amortization_schedule() if entry.year == 1),
        start=Decimal("0"),
    )


def _interest_first_year_total(loans: LoanSchedule) -> Decimal:
    return sum(
        (entry.interest for entry in loans.amortization_schedule() if entry.year == 1),
        start=Decimal("0"),
    )


def _projection_horizon(capex: CapexPlan, loans: LoanSchedule) -> int:
    capex_months = [entry.absolute_month for entry in capex.payment_schedule()]
    loan_months = [entry.absolute_month for entry in loans.amortization_schedule()]
    max_month = max([12, *capex_months, *loan_months]) if (capex_months or loan_months) else 12
    return max(max_month, DEFAULT_PROJECTION_MONTHS)


def _monthly_discount_rate(annual_rate: Decimal) -> Decimal:
    annual_rate = max(Decimal("0"), Decimal(annual_rate))
    monthly = (1.0 + float(annual_rate)) ** (1.0 / 12.0) - 1.0
    return Decimal(str(monthly))


def _project_cash_flows(
    operating_cf_after_interest: Decimal,
    capex: CapexPlan,
    loans: LoanSchedule,
    *,
    discount_rate: Decimal,
    projection_months: int,
) -> Tuple[List[Dict[str, Decimal]], Decimal | None, Decimal]:
    monthly_after_interest = (
        operating_cf_after_interest / Decimal("12") if operating_cf_after_interest else Decimal("0")
    )
    capex_schedule = capex.payments_by_month()
    loan_by_month = loans.debt_service_by_month()
    monthly_flows: List[Dict[str, Decimal]] = []
    cumulative = Decimal("0")
    payback_month: Decimal | None = None

    monthly_rate = _monthly_discount_rate(discount_rate)
    npv = Decimal("0")

    for month in range(1, projection_months + 1):
        year = (month - 1) // 12 + 1
        month_in_year = ((month - 1) % 12) + 1
        interest_month = loan_by_month.get(month, {}).get("interest", Decimal("0"))
        principal_month = loan_by_month.get(month, {}).get("principal", Decimal("0"))
        operating_pre_interest = monthly_after_interest + interest_month
        investing_cf = -capex_schedule.get(month, Decimal("0"))
        financing_cf = -(interest_month + principal_month)
        net = operating_pre_interest + investing_cf + financing_cf
        cumulative += net
        entry = {
            "month_index": Decimal(month),
            "year": Decimal(year),
            "month": Decimal(month_in_year),
            "operating": operating_pre_interest,
            "investing": investing_cf,
            "financing": financing_cf,
            "interest": interest_month,
            "principal": principal_month,
            "net": net,
            "cumulative": cumulative,
        }
        monthly_flows.append(entry)

        if payback_month is None and cumulative >= Decimal("0"):
            prev_cumulative = cumulative - net
            shortfall = -prev_cumulative
            fraction = Decimal("0")
            if net > Decimal("0") and shortfall > Decimal("0"):
                fraction = min(Decimal("1"), max(Decimal("0"), shortfall / net))
            payback_month = Decimal(month - 1) + fraction

        if monthly_rate > Decimal("-1"):
            discount_factor = (Decimal("1") + monthly_rate) ** month
            if discount_factor != Decimal("0"):
                npv += net / discount_factor

    return monthly_flows, payback_month, npv


def generate_cash_flow(
    pl_amounts: Dict[str, Decimal],
    capex: CapexPlan,
    loans: LoanSchedule,
    tax: TaxPolicy,
) -> Dict[str, object]:
    """Compute cash flow metrics, repayment schedules and investment indicators."""

    ordinary_income = Decimal(pl_amounts.get("ORD", Decimal("0")))
    depreciation = Decimal(pl_amounts.get("OPEX_DEP", Decimal("0")))
    income_tax_breakdown = tax.income_tax_components(ordinary_income)
    taxes = income_tax_breakdown["total"]

    net_income = ordinary_income - taxes
    operating_cf = ordinary_income + depreciation - taxes

    capex_total_first_year = _capex_first_year_total(capex)
    principal_total_first_year = _principal_first_year_total(loans)
    interest_total_first_year = _interest_first_year_total(loans)

    investing_cf = -capex_total_first_year
    financing_cf = -principal_total_first_year
    net_cf = operating_cf + investing_cf + financing_cf

    schedule_entries: List[LoanPayment] = loans.amortization_schedule()
    loan_schedule = [entry.to_dict() for entry in schedule_entries]
    capex_schedule = [entry.to_dict() for entry in capex.payment_schedule()]

    discount_rate = loans.weighted_average_interest_rate()
    if discount_rate <= Decimal("0"):
        discount_rate = DEFAULT_DISCOUNT_RATE

    projection_months = _projection_horizon(capex, loans)
    monthly_projection, payback_month, npv = _project_cash_flows(
        operating_cf,
        capex,
        loans,
        discount_rate=discount_rate,
        projection_months=projection_months,
    )
    payback_years = (payback_month / Decimal("12")) if payback_month is not None else None

    return {
        "営業キャッシュフロー": operating_cf,
        "投資キャッシュフロー": investing_cf,
        "財務キャッシュフロー": financing_cf,
        "キャッシュ増減": net_cf,
        "税引後利益": net_income,
        "減価償却": depreciation,
        "営業キャッシュフロー（利払前）": operating_cf + interest_total_first_year,
        "税金内訳": income_tax_breakdown,
        "loan_schedule": loan_schedule,
        "capex_schedule": capex_schedule,
        "investment_metrics": {
            "payback_period_months": payback_month,
            "payback_period_years": payback_years,
            "npv": npv,
            "discount_rate": discount_rate,
            "monthly_cash_flows": monthly_projection,
        },
    }


__all__ = ["generate_cash_flow"]
