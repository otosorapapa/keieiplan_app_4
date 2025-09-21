"""Cash flow estimation utilities."""
from __future__ import annotations

from decimal import Decimal
from typing import Dict

from models import CapexPlan, LoanSchedule, TaxPolicy


def generate_cash_flow(
    pl_amounts: Dict[str, Decimal],
    capex: CapexPlan,
    loans: LoanSchedule,
    tax: TaxPolicy,
) -> Dict[str, Decimal]:
    """Compute a simple cash flow statement using annual totals."""

    ordinary_income = Decimal(pl_amounts.get("ORD", Decimal("0")))
    depreciation = Decimal(pl_amounts.get("OPEX_DEP", Decimal("0")))
    taxes = tax.effective_tax(ordinary_income)

    net_income = ordinary_income - taxes
    operating_cf = ordinary_income + depreciation - taxes
    investing_cf = -capex.total_investment()
    financing_cf = -(loans.annual_interest())

    net_cf = operating_cf + investing_cf + financing_cf

    return {
        "営業キャッシュフロー": operating_cf,
        "投資キャッシュフロー": investing_cf,
        "財務キャッシュフロー": financing_cf,
        "キャッシュ増減": net_cf,
        "税引後利益": net_income,
        "減価償却": depreciation,
    }


__all__ = ["generate_cash_flow"]
