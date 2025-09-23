"""P&L related calculations built on top of typed financial models."""
from __future__ import annotations

from decimal import Decimal, getcontext
from typing import Dict, List, Tuple

import pandas as pd

from models import (
    CapexPlan,
    CostPlan,
    LoanSchedule,
    SalesPlan,
    TaxPolicy,
)

getcontext().prec = 28

ITEMS: List[Tuple[str, str, str]] = [
    ("REV", "売上高", "売上"),
    ("COGS_MAT", "外部仕入｜材料費", "外部仕入"),
    ("COGS_LBR", "外部仕入｜労務費(外部)", "外部仕入"),
    ("COGS_OUT_SRC", "外部仕入｜外注費(専属)", "外部仕入"),
    ("COGS_OUT_CON", "外部仕入｜外注費(委託)", "外部仕入"),
    ("COGS_OTH", "外部仕入｜その他諸経費", "外部仕入"),
    ("COGS_TTL", "外部仕入｜計", "外部仕入"),
    ("GROSS", "粗利(加工高)", "粗利"),
    ("OPEX_H", "内部費用｜人件費", "内部費用"),
    ("OPEX_AD", "内部費用｜広告宣伝費", "内部費用"),
    ("OPEX_UTIL", "内部費用｜水道光熱費", "内部費用"),
    ("OPEX_OTH", "内部費用｜その他販管費", "内部費用"),
    ("OPEX_DEP", "内部費用｜減価償却費", "内部費用"),
    ("OPEX_TTL", "内部費用｜計", "内部費用"),
    ("OP", "営業利益", "損益"),
    ("NOI_MISC", "営業外収益｜雑収入", "営業外"),
    ("NOI_GRANT", "営業外収益｜補助金/給付金", "営業外"),
    ("NOI_OTH", "営業外収益｜その他", "営業外"),
    ("NOE_INT", "営業外費用｜支払利息", "営業外"),
    ("NOE_OTH", "営業外費用｜雑損", "営業外"),
    ("ORD", "経常利益", "損益"),
    ("BE_SALES", "損益分岐点売上高", "KPI"),
    ("PC_SALES", "一人当たり売上", "KPI"),
    ("PC_GROSS", "一人当たり粗利", "KPI"),
    ("PC_ORD", "一人当たり経常利益", "KPI"),
    ("LDR", "労働分配率", "KPI"),
]

ITEM_LABELS = {code: label for code, label, _ in ITEMS}


class PlanConfig:
    """Holds calculation settings for the simplified contribution model."""

    def __init__(self, base_sales: Decimal, fte: Decimal, unit: str) -> None:
        self.base_sales = Decimal(base_sales)
        self.fte = Decimal(fte if fte else Decimal("0"))
        if self.fte <= 0:
            self.fte = Decimal("0.0001")
        self.unit = unit
        self.items: Dict[str, Dict[str, object]] = {}

    def set_rate(self, code: str, rate: Decimal, rate_base: str = "sales") -> None:
        self.items[code] = {
            "method": "rate",
            "value": Decimal(rate),
            "rate_base": rate_base,
        }

    def set_amount(self, code: str, amount: Decimal) -> None:
        self.items[code] = {
            "method": "amount",
            "value": Decimal(amount),
            "rate_base": "fixed",
        }

    def add_amount(self, code: str, amount: Decimal) -> None:
        amount = Decimal(amount)
        if code in self.items and self.items[code].get("method") == "amount":
            self.items[code]["value"] = Decimal(self.items[code]["value"]) + amount
        else:
            self.set_amount(code, amount)

    def clone(self) -> "PlanConfig":
        cloned = PlanConfig(self.base_sales, self.fte, self.unit)
        cloned.items = {k: v.copy() for k, v in self.items.items()}
        return cloned


COST_CODES = ["COGS_MAT", "COGS_LBR", "COGS_OUT_SRC", "COGS_OUT_CON", "COGS_OTH"]
OPEX_CODES = ["OPEX_H", "OPEX_AD", "OPEX_UTIL", "OPEX_OTH", "OPEX_DEP"]
NOI_CODES = ["NOI_MISC", "NOI_GRANT", "NOI_OTH"]
NOE_CODES = ["NOE_INT", "NOE_OTH"]


def plan_from_models(
    sales: SalesPlan,
    costs: CostPlan,
    capex: CapexPlan,
    loans: LoanSchedule,
    tax: TaxPolicy,
    *,
    fte: Decimal,
    unit: str,
) -> PlanConfig:
    """Build a :class:`PlanConfig` from typed models."""

    # Tax policy is forwarded to downstream cash-flow logic; the P&L plan focuses on operating figures.
    _ = tax

    base_sales = sales.annual_total()
    plan = PlanConfig(base_sales=base_sales, fte=fte, unit=unit)

    for code, ratio in costs.variable_ratios.items():
        plan.set_rate(code, Decimal(ratio), rate_base="sales")
    for code, ratio in costs.gross_linked_ratios.items():
        plan.set_rate(code, Decimal(ratio), rate_base="gross")
    for code, amount in costs.fixed_costs.items():
        plan.add_amount(code, Decimal(amount))
    for code, amount in costs.non_operating_income.items():
        plan.add_amount(code, Decimal(amount))
    for code, amount in costs.non_operating_expenses.items():
        plan.add_amount(code, Decimal(amount))

    depreciation = capex.annual_depreciation()
    if depreciation > 0:
        plan.add_amount("OPEX_DEP", depreciation)

    interest = loans.annual_interest()
    if interest > 0:
        plan.add_amount("NOE_INT", interest)

    # The tax policy is not directly embedded here; downstream calculations use it.
    return plan


def _line_amount(
    plan: PlanConfig,
    code: str,
    gross_guess: Decimal,
    sales: Decimal,
    amount_overrides: Dict[str, Decimal] | None,
) -> Decimal:
    if amount_overrides and code in amount_overrides:
        return Decimal(amount_overrides[code])
    cfg = plan.items.get(code)
    if cfg is None:
        return Decimal("0")
    method = cfg.get("method")
    value = Decimal(cfg.get("value", Decimal("0")))
    base = str(cfg.get("rate_base", "sales"))
    if method == "amount":
        return value
    if base == "sales":
        return sales * value
    if base == "gross":
        return max(Decimal("0"), gross_guess) * value
    if base == "fixed":
        return value
    return sales * value


def compute(
    plan: PlanConfig,
    sales_override: Decimal | None = None,
    amount_overrides: Dict[str, Decimal] | None = None,
) -> Dict[str, Decimal]:
    sales = Decimal(plan.base_sales if sales_override is None else sales_override)
    amounts: Dict[str, Decimal] = {code: Decimal("0") for code, *_ in ITEMS}
    amounts["REV"] = sales

    gross_guess = sales
    for _ in range(5):
        cogs = sum(
            max(Decimal("0"), _line_amount(plan, code, gross_guess, sales, amount_overrides))
            for code in COST_CODES
        )
        new_gross = sales - cogs
        if abs(new_gross - gross_guess) < Decimal("0.0001"):
            gross_guess = new_gross
            break
        gross_guess = new_gross

    cogs_total = Decimal("0")
    for code in COST_CODES:
        val = max(Decimal("0"), _line_amount(plan, code, gross_guess, sales, amount_overrides))
        amounts[code] = val
        cogs_total += val
    amounts["COGS_TTL"] = cogs_total
    amounts["GROSS"] = sales - cogs_total

    opex_total = Decimal("0")
    for code in OPEX_CODES:
        val = max(Decimal("0"), _line_amount(plan, code, amounts["GROSS"], sales, amount_overrides))
        amounts[code] = val
        opex_total += val
    amounts["OPEX_TTL"] = opex_total
    amounts["OP"] = amounts["GROSS"] - amounts["OPEX_TTL"]

    for code in NOI_CODES + NOE_CODES:
        val = max(Decimal("0"), _line_amount(plan, code, amounts["GROSS"], sales, amount_overrides))
        amounts[code] = val

    amounts["ORD"] = amounts["OP"] + (
        amounts["NOI_MISC"] + amounts["NOI_GRANT"] + amounts["NOI_OTH"]
    ) - (amounts["NOE_INT"] + amounts["NOE_OTH"])

    variable_cost = Decimal("0")
    for code in COST_CODES + OPEX_CODES + NOI_CODES + NOE_CODES:
        cfg = plan.items.get(code)
        if cfg and cfg.get("method") == "rate":
            base = str(cfg.get("rate_base", "sales"))
            rate = Decimal(cfg.get("value", Decimal("0")))
            if base == "gross":
                gross_ratio = amounts["GROSS"] / sales if sales > 0 else Decimal("0")
                variable_cost += sales * (rate * gross_ratio)
            else:
                variable_cost += sales * rate

    fixed_cost = Decimal("0")
    for code in COST_CODES + OPEX_CODES + NOI_CODES + NOE_CODES:
        cfg = plan.items.get(code)
        if cfg and cfg.get("method") == "amount":
            fixed_cost += Decimal(cfg.get("value", Decimal("0")))
        elif cfg and str(cfg.get("rate_base")) == "fixed":
            fixed_cost += Decimal(cfg.get("value", Decimal("0")))

    contribution_ratio = Decimal("1") - (variable_cost / sales if sales > 0 else Decimal("0"))
    if contribution_ratio <= 0:
        amounts["BE_SALES"] = Decimal("Infinity")
    else:
        amounts["BE_SALES"] = fixed_cost / contribution_ratio

    fte = plan.fte if plan.fte > 0 else Decimal("1")
    amounts["PC_SALES"] = amounts["REV"] / fte
    amounts["PC_GROSS"] = amounts["GROSS"] / fte
    amounts["PC_ORD"] = amounts["ORD"] / fte
    amounts["LDR"] = (
        amounts["OPEX_H"] / amounts["GROSS"] if amounts["GROSS"] > 0 else Decimal("NaN")
    )

    return amounts


def compute_plan(plan: Dict[str, Decimal]) -> Dict[str, Decimal]:
    sales = Decimal(plan.get("sales", Decimal("0")))
    gp_rate = Decimal(plan.get("gp_rate", Decimal("0")))
    gross = sales * gp_rate
    opex_h = Decimal(plan.get("opex_h", Decimal("0")))
    opex_fixed = Decimal(plan.get("opex_fixed", Decimal("0")))
    opex_dep = Decimal(plan.get("opex_dep", Decimal("0")))
    opex_oth = Decimal(plan.get("opex_oth", Decimal("0")))
    op = gross - opex_h - opex_fixed - opex_dep - opex_oth
    return {
        "sales": sales,
        "gp_rate": gp_rate,
        "gross": gross,
        "opex_h": opex_h,
        "opex_fixed": opex_fixed,
        "opex_dep": opex_dep,
        "opex_oth": opex_oth,
        "op": op,
        "ord": op,
    }


def summarize_plan_metrics(amounts: Dict[str, Decimal]) -> Dict[str, Decimal]:
    sales = Decimal(amounts.get("REV", Decimal("0")))
    gross = Decimal(amounts.get("GROSS", Decimal("0")))
    op = Decimal(amounts.get("OP", Decimal("0")))
    ord_val = Decimal(amounts.get("ORD", Decimal("0")))
    opex = Decimal(amounts.get("OPEX_TTL", Decimal("0")))
    cogs = Decimal(amounts.get("COGS_TTL", sales - gross))

    def safe_ratio(num: Decimal, den: Decimal) -> Decimal:
        return num / den if den not in (Decimal("0"), Decimal("NaN")) else Decimal("NaN")

    metrics = {
        "sales": sales,
        "gross": gross,
        "op": op,
        "ord": ord_val,
        "gross_margin": safe_ratio(gross, sales),
        "op_margin": safe_ratio(op, sales),
        "ord_margin": safe_ratio(ord_val, sales),
        "cogs_ratio": safe_ratio(cogs, sales),
        "opex_ratio": safe_ratio(opex, sales),
        "labor_ratio": safe_ratio(Decimal(amounts.get("OPEX_H", Decimal("0"))), gross),
        "breakeven": Decimal(amounts.get("BE_SALES", Decimal("NaN"))),
    }
    return metrics


def _ord_from(result: Dict[str, Decimal], nonop: Dict[str, Decimal]) -> Decimal:
    noi = nonop.get("noi_misc", Decimal("0")) + nonop.get("noi_grant", Decimal("0"))
    noe = nonop.get("noe_int", Decimal("0")) + nonop.get("noe_oth", Decimal("0"))
    return result["op"] + noi - noe


def _plan_with(plan: Dict[str, Decimal], **overrides: Decimal) -> Dict[str, Decimal]:
    new_plan = plan.copy()
    new_plan.update(overrides)
    return new_plan


def _line_items(result: Dict[str, Decimal], nonop: Dict[str, Decimal]) -> Dict[str, Decimal]:
    rev = result["sales"]
    gross = result["gross"]
    cogs_total = rev - gross
    opex_total = result["opex_fixed"] + result["opex_h"] + result["opex_dep"] + result["opex_oth"]
    ord_value = _ord_from(result, nonop)
    return {
        "REV": rev,
        "COGS_TTL": cogs_total,
        "GROSS": gross,
        "OPEX_H": result["opex_h"],
        "OPEX_FIXED": result["opex_fixed"],
        "OPEX_DEP": result["opex_dep"],
        "OPEX_OTH": result["opex_oth"],
        "OPEX_TTL": opex_total,
        "OP": result["op"],
        "NOI_MISC": nonop.get("noi_misc", Decimal("0")),
        "NOI_GRANT": nonop.get("noi_grant", Decimal("0")),
        "NOE_INT": nonop.get("noe_int", Decimal("0")),
        "NOE_OTH": nonop.get("noe_oth", Decimal("0")),
        "ORD": ord_value,
    }


def _required_sales_for_ord(target_ord: Decimal, plan: Dict[str, Decimal], nonop: Dict[str, Decimal]) -> Decimal:
    gp = max(Decimal("1e-9"), Decimal(plan["gp_rate"]))
    opex_total = plan["opex_fixed"] + plan["opex_h"] + plan["opex_dep"] + plan["opex_oth"]
    noi = nonop.get("noi_misc", Decimal("0")) + nonop.get("noi_grant", Decimal("0"))
    noe = nonop.get("noe_int", Decimal("0")) + nonop.get("noe_oth", Decimal("0"))
    return (target_ord + opex_total - noi + noe) / gp


def _be_sales(plan: Dict[str, Decimal], nonop: Dict[str, Decimal], *, mode: str = "OP") -> Decimal:
    gp = max(Decimal("1e-9"), Decimal(plan["gp_rate"]))
    opex_total = plan["opex_fixed"] + plan["opex_h"] + plan["opex_dep"] + plan["opex_oth"]
    noi = nonop.get("noi_misc", Decimal("0")) + nonop.get("noi_grant", Decimal("0"))
    noe = nonop.get("noe_int", Decimal("0")) + nonop.get("noe_oth", Decimal("0"))
    if mode == "ORD":
        return (opex_total - noi + noe) / gp
    return opex_total / gp


def build_scenario_dataframe(
    base_plan: Dict[str, Decimal],
    plan: Dict[str, Decimal],
    nonop: Dict[str, Decimal] | None = None,
    target_ord: Decimal = Decimal("50000000"),
    be_mode: str = "OP",
) -> pd.DataFrame:
    nonop = {
        "noi_misc": Decimal("0"),
        "noi_grant": Decimal("0"),
        "noe_int": Decimal("0"),
        "noe_oth": Decimal("0"),
    } if nonop is None else {k: Decimal(v) for k, v in nonop.items()}

    result_target = compute_plan(plan)
    col_target = _line_items(result_target, nonop)

    def col_sales_scale(scale: Decimal) -> Dict[str, Decimal]:
        scaled = _plan_with(plan, sales=plan["sales"] * scale)
        return _line_items(compute_plan(scaled), nonop)

    col_sales_up = col_sales_scale(Decimal("1.10"))
    col_sales_dn5 = col_sales_scale(Decimal("0.95"))
    col_sales_dn10 = col_sales_scale(Decimal("0.90"))

    gp_up = _plan_with(plan, gp_rate=min(Decimal("1"), plan["gp_rate"] + Decimal("0.01")))
    col_gp_up = _line_items(compute_plan(gp_up), nonop)

    required_sales = max(Decimal("0"), _required_sales_for_ord(target_ord, plan, nonop))
    plan_for_ord = _plan_with(plan, sales=required_sales)
    col_ord = _line_items(compute_plan(plan_for_ord), nonop)

    col_last = _line_items(compute_plan(base_plan), nonop)

    be_sales = max(Decimal("0"), _be_sales(plan, nonop, mode=be_mode))
    plan_be = _plan_with(plan, sales=be_sales)
    col_be = _line_items(compute_plan(plan_be), nonop)

    df = pd.DataFrame.from_dict(
        {
            "目標": col_target,
            "売上高10%増": col_sales_up,
            "売上高5%減": col_sales_dn5,
            "売上高10%減": col_sales_dn10,
            "粗利率+1pt": col_gp_up,
            "経常利益5千万円": col_ord,
            "昨年同一": col_last,
            "損益分岐点売上高": col_be,
        },
        orient="index",
    ).T
    return df


def bisection_for_target_op(
    plan: PlanConfig,
    target_op: Decimal,
    s_low: Decimal,
    s_high: Decimal,
    *,
    max_iter: int = 60,
    eps: Decimal = Decimal("1000"),
) -> Tuple[Decimal, Dict[str, Decimal]]:
    def op_at(value: Decimal) -> Decimal:
        return compute(plan, sales_override=value)["ORD"]

    low = max(Decimal("0"), s_low)
    high = max(s_low * Decimal("1.5"), s_high)
    f_low = op_at(low)
    f_high = op_at(high)
    iterations = 0
    while (f_low - target_op) * (f_high - target_op) > 0 and high < Decimal("1e13") and iterations < 40:
        high = high * Decimal("1.6") if high > 0 else Decimal("1000000")
        f_high = op_at(high)
        iterations += 1

    for _ in range(max_iter):
        mid = (low + high) / Decimal("2")
        f_mid = op_at(mid)
        if abs(f_mid - target_op) <= eps:
            return mid, compute(plan, sales_override=mid)
        if (f_low - target_op) * (f_mid - target_op) <= 0:
            high, f_high = mid, f_mid
        else:
            low, f_low = mid, f_mid

    mid = (low + high) / Decimal("2")
    return mid, compute(plan, sales_override=mid)


__all__ = [
    "ITEMS",
    "ITEM_LABELS",
    "PlanConfig",
    "plan_from_models",
    "compute",
    "compute_plan",
    "summarize_plan_metrics",
    "build_scenario_dataframe",
    "bisection_for_target_op",
]
