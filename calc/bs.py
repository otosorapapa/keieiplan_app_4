"""Simple balance sheet estimation utilities."""
from __future__ import annotations

from decimal import Decimal
from typing import Dict

from models import CapexPlan, LoanSchedule, TaxPolicy


def generate_balance_sheet(
    pl_amounts: Dict[str, Decimal],
    capex: CapexPlan,
    loans: LoanSchedule,
    tax: TaxPolicy,
) -> Dict[str, Dict[str, Decimal]]:
    """Return a lightweight balance sheet derived from P&L outputs."""

    ordinary_income = Decimal(pl_amounts.get("ORD", Decimal("0")))
    taxes = tax.effective_tax(ordinary_income)
    retained = ordinary_income - taxes
    if retained < 0:
        retained = Decimal("0")

    cash = retained
    gross_capex = capex.total_investment()
    accumulated_dep = capex.annual_depreciation()
    net_pp_e = max(Decimal("0"), gross_capex - accumulated_dep)

    assets_total = cash + net_pp_e

    debt = loans.outstanding_principal()
    equity = assets_total - debt

    assets = {
        "現金同等物": cash,
        "有形固定資産": net_pp_e,
    }
    liabilities = {
        "有利子負債": debt,
        "純資産": equity,
    }
    totals = {
        "assets": assets_total,
        "liabilities": debt + equity,
    }
    return {"assets": assets, "liabilities": liabilities, "totals": totals}


__all__ = ["generate_balance_sheet"]
