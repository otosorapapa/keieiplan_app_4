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
    *,
    working_capital: Dict[str, float] | None = None,
) -> Dict[str, Dict[str, Decimal]]:
    """Return an estimated balance sheet derived from P&L outputs."""

    ordinary_income = Decimal(pl_amounts.get("ORD", Decimal("0")))
    depreciation = Decimal(pl_amounts.get("OPEX_DEP", Decimal("0")))
    taxes = tax.effective_tax(ordinary_income)
    net_income = ordinary_income - taxes

    operating_cf = ordinary_income + depreciation - taxes
    investing_cf = -capex.total_investment()
    financing_cf = -(loans.annual_interest())
    cash = operating_cf + investing_cf + financing_cf

    gross_capex = capex.total_investment()
    accumulated_dep = capex.annual_depreciation()
    net_pp_e = max(Decimal("0"), gross_capex - accumulated_dep)

    wc = working_capital or {}
    receivable_days = Decimal(str(wc.get("receivable_days", 45.0)))
    inventory_days = Decimal(str(wc.get("inventory_days", 30.0)))
    payable_days = Decimal(str(wc.get("payable_days", 25.0)))

    annual_sales = Decimal(pl_amounts.get("REV", Decimal("0")))
    annual_cogs = Decimal(pl_amounts.get("COGS_TTL", Decimal("0")))
    daily_sales = annual_sales / Decimal("365") if annual_sales > 0 else Decimal("0")
    daily_cogs = annual_cogs / Decimal("365") if annual_cogs > 0 else Decimal("0")

    accounts_receivable = daily_sales * receivable_days
    inventory = daily_cogs * inventory_days
    accounts_payable = daily_cogs * payable_days

    assets_total = cash + accounts_receivable + inventory + net_pp_e

    interest_bearing_debt = loans.outstanding_principal()
    total_liabilities = interest_bearing_debt + accounts_payable
    equity = assets_total - total_liabilities

    assets = {
        "現金同等物": cash,
        "売掛金": accounts_receivable,
        "棚卸資産": inventory,
        "有形固定資産": net_pp_e,
    }
    liabilities = {
        "買掛金": accounts_payable,
        "有利子負債": interest_bearing_debt,
        "純資産": equity,
    }
    totals = {
        "assets": assets_total,
        "liabilities": total_liabilities,
    }
    metrics = {
        "net_income": net_income,
        "equity_ratio": equity / assets_total if assets_total > 0 else Decimal("NaN"),
        "roe": net_income / equity if equity > 0 else Decimal("NaN"),
        "working_capital": accounts_receivable + inventory - accounts_payable,
        "receivable_days": receivable_days,
        "inventory_days": inventory_days,
        "payable_days": payable_days,
    }
    return {
        "assets": assets,
        "liabilities": liabilities,
        "totals": totals,
        "metrics": metrics,
    }


__all__ = ["generate_balance_sheet"]
