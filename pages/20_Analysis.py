"""Analytics page showing KPI dashboard, break-even analysis and cash flow."""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from calc import (
    ITEMS,
    compute,
    generate_balance_sheet,
    generate_cash_flow,
    plan_from_models,
    summarize_plan_metrics,
)
from formatting import UNIT_FACTORS, format_amount_with_unit, format_ratio
from state import ensure_session_defaults, load_finance_bundle
from models import INDUSTRY_TEMPLATES, CapexPlan, LoanSchedule
from theme import COLOR_BLIND_COLORS, THEME_COLORS, inject_theme
from ui.components import MetricCard, render_metric_cards
from ui.streamlit_compat import use_container_width_kwargs

ITEM_LABELS = {code: label for code, label, _ in ITEMS}

PLOTLY_DOWNLOAD_OPTIONS = {
    "format": "png",
    "height": 600,
    "width": 1000,
    "scale": 2,
}

def _accessible_palette() -> List[str]:
    palette_source = COLOR_BLIND_COLORS if st.session_state.get("ui_color_blind", False) else THEME_COLORS
    return [
        palette_source["chart_blue"],
        palette_source["chart_orange"],
        palette_source["chart_green"],
        palette_source["chart_purple"],
        "#8c564b",
        "#e377c2",
    ]


def plotly_download_config(name: str) -> Dict[str, object]:
    """Ensure every Plotly chart exposes an image download button."""

    return {
        "displaylogo": False,
        "toImageButtonOptions": {"filename": name, **PLOTLY_DOWNLOAD_OPTIONS},
    }


def _to_decimal(value: object) -> Decimal:
    return Decimal(str(value))


@st.cache_data(show_spinner=False)
def build_monthly_pl_dataframe(
    sales_data: Dict[str, object],
    plan_items: Dict[str, Dict[str, str]],
    amounts_data: Dict[str, str],
) -> pd.DataFrame:
    monthly_sales = {month: Decimal("0") for month in range(1, 13)}
    for item in sales_data.get("items", []):
        monthly = item.get("monthly", {})
        amounts = monthly.get("amounts", [])
        for idx, month in enumerate(range(1, 13)):
            value = amounts[idx] if idx < len(amounts) else 0
            monthly_sales[month] += _to_decimal(value)

    total_sales = _to_decimal(amounts_data.get("REV", "0"))
    total_gross = _to_decimal(amounts_data.get("GROSS", "0"))
    gross_ratio = total_gross / total_sales if total_sales else Decimal("0")

    rows: List[Dict[str, float]] = []
    for month in range(1, 13):
        sales = monthly_sales.get(month, Decimal("0"))
        monthly_gross = sales * gross_ratio
        cogs = Decimal("0")
        opex = Decimal("0")
        for code, cfg in plan_items.items():
            method = str(cfg.get("method", ""))
            base = str(cfg.get("rate_base", "sales"))
            value = _to_decimal(cfg.get("value", "0"))
            if not code.startswith(("COGS", "OPEX")):
                continue
            if method == "rate":
                if base == "gross":
                    amount = monthly_gross * value
                elif base == "sales":
                    amount = sales * value
                else:
                    amount = value
            else:
                amount = value / Decimal("12")
            if code.startswith("COGS"):
                cogs += amount
            else:
                opex += amount
        gross = sales - cogs
        op = gross - opex
        gross_margin = gross / sales if sales else Decimal("0")
        rows.append(
            {
                "month": f"{month}月",
                "売上高": float(sales),
                "売上原価": float(cogs),
                "販管費": float(opex),
                "営業利益": float(op),
                "粗利": float(gross),
                "粗利率": float(gross_margin),
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def build_cost_composition(amounts_data: Dict[str, str]) -> pd.DataFrame:
    component_codes = [
        "COGS_MAT",
        "COGS_LBR",
        "COGS_OUT_SRC",
        "COGS_OUT_CON",
        "COGS_OTH",
        "OPEX_H",
        "OPEX_AD",
        "OPEX_UTIL",
        "OPEX_OTH",
        "OPEX_DEP",
        "NOE_INT",
        "NOE_OTH",
    ]
    rows: List[Dict[str, float]] = []
    for code in component_codes:
        value = _to_decimal(amounts_data.get(code, "0"))
        if value <= 0:
            continue
        rows.append({"項目": ITEM_LABELS.get(code, code), "金額": float(value)})
    return pd.DataFrame(rows)


def _monthly_capex_schedule(capex: CapexPlan) -> Dict[int, Decimal]:
    schedule = {month: Decimal("0") for month in range(1, 13)}
    for entry in capex.payment_schedule():
        if entry.absolute_month <= 12:
            schedule[entry.absolute_month] += entry.amount
    return schedule


def _monthly_debt_schedule(loans: LoanSchedule) -> Dict[int, Dict[str, Decimal]]:
    schedule: Dict[int, Dict[str, Decimal]] = {}
    for entry in loans.amortization_schedule():
        if entry.absolute_month > 12:
            continue
        month_entry = schedule.setdefault(
            entry.absolute_month,
            {"interest": Decimal("0"), "principal": Decimal("0")},
        )
        month_entry["interest"] += entry.interest
        month_entry["principal"] += entry.principal
    return schedule


def _cost_structure(
    plan_items: Dict[str, Dict[str, str]], amounts_data: Dict[str, str]
) -> Tuple[Decimal, Decimal]:
    sales_total = _to_decimal(amounts_data.get("REV", "0"))
    gross_total = _to_decimal(amounts_data.get("GROSS", "0"))
    variable_cost = Decimal("0")
    fixed_cost = Decimal("0")
    for cfg in plan_items.values():
        method = str(cfg.get("method", ""))
        base = str(cfg.get("rate_base", "sales"))
        value = _to_decimal(cfg.get("value", "0"))
        if method == "rate":
            if base == "gross":
                ratio = gross_total / sales_total if sales_total else Decimal("0")
                variable_cost += sales_total * (value * ratio)
            elif base == "sales":
                variable_cost += sales_total * value
            elif base == "fixed":
                fixed_cost += value
        else:
            fixed_cost += value
    variable_rate = variable_cost / sales_total if sales_total else Decimal("0")
    return variable_rate, fixed_cost


@st.cache_data(show_spinner=False)
def build_cvp_dataframe(
    plan_items: Dict[str, Dict[str, str]], amounts_data: Dict[str, str]
) -> Tuple[pd.DataFrame, Decimal, Decimal, Decimal]:
    variable_rate, fixed_cost = _cost_structure(plan_items, amounts_data)
    sales_total = _to_decimal(amounts_data.get("REV", "0"))
    max_sales = sales_total * Decimal("1.3") if sales_total else Decimal("1000000")
    max_sales_float = max(float(max_sales), float(sales_total)) if sales_total else float(max_sales)
    sales_values = np.linspace(0, max_sales_float if max_sales_float > 0 else 1.0, 40)
    rows: List[Dict[str, float]] = []
    for sale in sales_values:
        sale_decimal = _to_decimal(sale)
        total_cost = fixed_cost + variable_rate * sale_decimal
        rows.append(
            {
                "売上高": float(sale_decimal),
                "総費用": float(total_cost),
            }
        )
    breakeven = _to_decimal(amounts_data.get("BE_SALES", "0"))
    return pd.DataFrame(rows), variable_rate, fixed_cost, breakeven


@st.cache_data(show_spinner=False)
def build_fcf_steps(
    amounts_data: Dict[str, str],
    tax_data: Dict[str, object],
    capex_data: Dict[str, object],
    loans_data: Dict[str, object],
) -> List[Dict[str, float]]:
    del loans_data  # 不要だがインターフェイスを合わせる
    ebit = _to_decimal(amounts_data.get("OP", "0"))
    corporate_rate = _to_decimal(tax_data.get("corporate_tax_rate", "0"))
    taxes = ebit * corporate_rate if ebit > 0 else Decimal("0")
    depreciation = _to_decimal(amounts_data.get("OPEX_DEP", "0"))
    working_capital = Decimal("0")
    capex_total = sum(
        (_to_decimal(item.get("amount", "0")) for item in capex_data.get("items", [])),
        start=Decimal("0"),
    )
    fcf = ebit - taxes + depreciation - working_capital - capex_total
    return [
        {"name": "EBIT", "value": float(ebit)},
        {"name": "税金", "value": float(-taxes)},
        {"name": "減価償却", "value": float(depreciation)},
        {"name": "運転資本", "value": float(-working_capital)},
        {"name": "CAPEX", "value": float(-capex_total)},
        {"name": "FCF", "value": float(fcf)},
    ]


@st.cache_data(show_spinner=False)
def build_dscr_timeseries(
    loans_data: Dict[str, object], operating_cf_value: str
) -> pd.DataFrame:
    operating_cf = _to_decimal(operating_cf_value)
    if operating_cf < 0:
        operating_cf = Decimal("0")
    try:
        schedule_model = LoanSchedule(**loans_data)
    except Exception:
        return pd.DataFrame()

    entries = schedule_model.amortization_schedule()
    if not entries:
        return pd.DataFrame()

    aggregated: Dict[int, Dict[str, Decimal]] = {}
    for entry in entries:
        data = aggregated.setdefault(
            int(entry.year),
            {"interest": Decimal("0"), "principal": Decimal("0"), "out_start": None},
        )
        data["interest"] += entry.interest
        data["principal"] += entry.principal
        if data["out_start"] is None:
            data["out_start"] = entry.balance + entry.principal

    grouped_rows: List[Dict[str, float]] = []
    for year, values in sorted(aggregated.items()):
        interest_total = values["interest"]
        principal_total = values["principal"]
        outstanding_start = values["out_start"] or Decimal("0")
        debt_service = interest_total + principal_total
        dscr = operating_cf / debt_service if debt_service > 0 else Decimal("NaN")
        payback_years = (
            outstanding_start / operating_cf if operating_cf > 0 else Decimal("NaN")
        )
        grouped_rows.append(
            {
                "年度": f"FY{year}",
                "DSCR": float(dscr),
                "債務償還年数": float(payback_years),
            }
        )
    return pd.DataFrame(grouped_rows)

st.set_page_config(
    page_title="経営計画スタジオ｜Analysis",
    page_icon="📈",
    layout="wide",
)

inject_theme()
ensure_session_defaults()

settings_state: Dict[str, object] = st.session_state.get("finance_settings", {})
unit = str(settings_state.get("unit", "百万円"))
fte = Decimal(str(settings_state.get("fte", 20)))
fiscal_year = int(settings_state.get("fiscal_year", 2025))
unit_factor = UNIT_FACTORS.get(unit, Decimal("1"))

bundle, has_custom_inputs = load_finance_bundle()
if not has_custom_inputs:
    st.info("Inputsページでデータを保存すると、分析結果が更新されます。以下は既定値サンプルです。")

plan_cfg = plan_from_models(
    bundle.sales,
    bundle.costs,
    bundle.capex,
    bundle.loans,
    bundle.tax,
    fte=fte,
    unit=unit,
)

amounts = compute(plan_cfg)
metrics = summarize_plan_metrics(amounts)
working_capital_profile = st.session_state.get("working_capital_profile", {})
palette = _accessible_palette()
bs_data = generate_balance_sheet(
    amounts,
    bundle.capex,
    bundle.loans,
    bundle.tax,
    working_capital=working_capital_profile,
)
cf_data = generate_cash_flow(amounts, bundle.capex, bundle.loans, bundle.tax)
sales_summary = bundle.sales.assumption_summary()
capex_schedule = _monthly_capex_schedule(bundle.capex)
debt_schedule = _monthly_debt_schedule(bundle.loans)
principal_schedule = {month: values["principal"] for month, values in debt_schedule.items()}
interest_schedule = {month: values["interest"] for month, values in debt_schedule.items()}
plan_sales_total = Decimal(amounts.get("REV", Decimal("0")))
sales_range_min = Decimal(sales_summary.get("range_min_total", Decimal("0")))
sales_range_typical = Decimal(sales_summary.get("range_typical_total", Decimal("0")))
sales_range_max = Decimal(sales_summary.get("range_max_total", Decimal("0")))
cost_range_totals = bundle.costs.aggregate_range_totals(plan_sales_total)
variable_cost_range = cost_range_totals["variable"]
fixed_cost_range = cost_range_totals["fixed"]
non_operating_range = cost_range_totals["non_operating"]

plan_items_serialized = {
    code: {
        "method": str(cfg.get("method", "")),
        "rate_base": str(cfg.get("rate_base", "sales")),
        "value": str(cfg.get("value", "0")),
    }
    for code, cfg in plan_cfg.items.items()
}
sales_dump = bundle.sales.model_dump(mode="json")
amounts_serialized = {code: str(value) for code, value in amounts.items()}
capex_dump = bundle.capex.model_dump(mode="json")
loans_dump = bundle.loans.model_dump(mode="json")
tax_dump = bundle.tax.model_dump(mode="json")

monthly_pl_df = build_monthly_pl_dataframe(sales_dump, plan_items_serialized, amounts_serialized)
cost_df = build_cost_composition(amounts_serialized)
cvp_df, variable_rate, fixed_cost, breakeven_sales = build_cvp_dataframe(
    plan_items_serialized, amounts_serialized
)
fcf_steps = build_fcf_steps(amounts_serialized, tax_dump, capex_dump, loans_dump)
operating_cf_str = str(cf_data.get("営業キャッシュフロー", Decimal("0")))
dscr_df = build_dscr_timeseries(loans_dump, operating_cf_str)
bs_metrics = bs_data.get("metrics", {})
cash_total = bs_data.get("assets", {}).get("現金同等物", Decimal("0"))
industry_template_key = str(st.session_state.get("selected_industry_template", ""))
industry_metric_state: Dict[str, Dict[str, float]] = st.session_state.get(
    "industry_custom_metrics", {}
)
external_actuals: Dict[str, Dict[str, object]] = st.session_state.get("external_actuals", {})

depreciation_total = Decimal(amounts.get("OPEX_DEP", Decimal("0")))
monthly_depreciation = depreciation_total / Decimal("12") if depreciation_total else Decimal("0")
non_operating_income_total = sum(
    (Decimal(amounts.get(code, Decimal("0"))) for code in ["NOI_MISC", "NOI_GRANT", "NOI_OTH"]),
    start=Decimal("0"),
)
non_operating_expense_total = sum(
    (Decimal(amounts.get(code, Decimal("0"))) for code in ["NOE_INT", "NOE_OTH"]),
    start=Decimal("0"),
)
interest_expense_total = Decimal(amounts.get("NOE_INT", Decimal("0")))
other_non_operating_expense_total = non_operating_expense_total - interest_expense_total
monthly_noi = non_operating_income_total / Decimal("12") if non_operating_income_total else Decimal("0")
monthly_other_noe = (
    other_non_operating_expense_total / Decimal("12") if other_non_operating_expense_total else Decimal("0")
)
tax_rate = Decimal(bundle.tax.corporate_tax_rate)

monthly_cf_entries: List[Dict[str, Decimal]] = []
running_cash = Decimal("0")
for idx, row in monthly_pl_df.iterrows():
    month_index = idx + 1
    operating_profit = Decimal(str(row["営業利益"]))
    interest_month = interest_schedule.get(month_index, Decimal("0"))
    monthly_noe = monthly_other_noe + interest_month
    ordinary_income_month = operating_profit + monthly_noi - monthly_noe
    taxes_month = ordinary_income_month * tax_rate if ordinary_income_month > 0 else Decimal("0")
    operating_cf_month = ordinary_income_month + monthly_depreciation - taxes_month
    investing_cf_month = -capex_schedule.get(month_index, Decimal("0"))
    financing_cf_month = -principal_schedule.get(month_index, Decimal("0"))
    net_cf_month = operating_cf_month + investing_cf_month + financing_cf_month
    running_cash += net_cf_month
    monthly_cf_entries.append(
        {
            "month": row["month"],
            "operating": operating_cf_month,
            "investing": investing_cf_month,
            "financing": financing_cf_month,
            "taxes": taxes_month,
            "net": net_cf_month,
            "cumulative": running_cash,
        }
    )

if monthly_cf_entries:
    desired_cash = cash_total
    diff = desired_cash - monthly_cf_entries[-1]["cumulative"]
    if abs(diff) > Decimal("1"):
        adjustment = diff / Decimal(len(monthly_cf_entries))
        running_cash = Decimal("0")
        for entry in monthly_cf_entries:
            entry["net"] += adjustment
            running_cash += entry["net"]
            entry["cumulative"] = running_cash

monthly_cf_df = pd.DataFrame(
    [
        {
            "月": entry["month"],
            "営業CF": float(entry["operating"]),
            "投資CF": float(entry["investing"]),
            "財務CF": float(entry["financing"]),
            "税金": float(entry["taxes"]),
            "月次純増減": float(entry["net"]),
            "累計キャッシュ": float(entry["cumulative"]),
        }
        for entry in monthly_cf_entries
    ]
)

ar_total = bs_data.get("assets", {}).get("売掛金", Decimal("0"))
inventory_total = bs_data.get("assets", {}).get("棚卸資産", Decimal("0"))
ap_total = bs_data.get("liabilities", {}).get("買掛金", Decimal("0"))
net_pp_e = bs_data.get("assets", {}).get("有形固定資産", Decimal("0"))
interest_debt_total = bs_data.get("liabilities", {}).get("有利子負債", Decimal("0"))
total_sales_decimal = Decimal(str(monthly_pl_df["売上高"].sum()))
total_cogs_decimal = Decimal(str(monthly_pl_df["売上原価"].sum()))

monthly_bs_rows: List[Dict[str, float]] = []
for idx, row in monthly_pl_df.iterrows():
    month_label = row["month"]
    sales = Decimal(str(row["売上高"]))
    cogs = Decimal(str(row["売上原価"]))
    sales_ratio = sales / total_sales_decimal if total_sales_decimal > 0 else Decimal("0")
    cogs_ratio = cogs / total_cogs_decimal if total_cogs_decimal > 0 else Decimal("0")
    ar_month = ar_total * sales_ratio
    inventory_month = inventory_total * cogs_ratio
    ap_month = ap_total * cogs_ratio
    cumulative_cash = (
        Decimal(str(monthly_cf_df.iloc[idx]["累計キャッシュ"])) if not monthly_cf_df.empty else Decimal("0")
    )
    equity_month = cumulative_cash + ar_month + inventory_month + net_pp_e - ap_month - interest_debt_total
    monthly_bs_rows.append(
        {
            "月": month_label,
            "現金同等物": float(cumulative_cash),
            "売掛金": float(ar_month),
            "棚卸資産": float(inventory_month),
            "有形固定資産": float(net_pp_e),
            "買掛金": float(ap_month),
            "有利子負債": float(interest_debt_total),
            "純資産": float(equity_month),
        }
    )

monthly_bs_df = pd.DataFrame(monthly_bs_rows)

st.title("📈 KPI・損益分析")
st.caption(f"FY{fiscal_year} / 表示単位: {unit} / FTE: {fte}")

kpi_tab, be_tab, cash_tab = st.tabs(["KPIダッシュボード", "損益分岐点", "資金繰り"])

with kpi_tab:
    st.subheader("主要KPI")

    def _amount_formatter(value: Decimal) -> str:
        return format_amount_with_unit(value, unit)

    def _yen_formatter(value: Decimal) -> str:
        return format_amount_with_unit(value, "円")

    def _count_formatter(value: Decimal) -> str:
        return f"{int(value)}人"

    def _frequency_formatter(value: Decimal) -> str:
        return f"{float(value):.2f}回"

    def _tone_threshold(value: Decimal, *, positive: Decimal, caution: Decimal) -> str:
        if value >= positive:
            return "positive"
        if value <= caution:
            return "caution"
        return "neutral"

    kpi_options: Dict[str, Dict[str, object]] = {
        "sales": {
            "label": "売上高",
            "value": Decimal(amounts.get("REV", Decimal("0"))),
            "formatter": _amount_formatter,
            "icon": "💴",
            "description": "年度売上の合計値",
        },
        "gross": {
            "label": "粗利",
            "value": Decimal(amounts.get("GROSS", Decimal("0"))),
            "formatter": _amount_formatter,
            "icon": "🧮",
            "description": "売上から原価を差し引いた利益",
            "tone_fn": lambda v: "negative" if v < Decimal("0") else "positive" if v > Decimal("0") else "neutral",
        },
        "op": {
            "label": "営業利益",
            "value": Decimal(amounts.get("OP", Decimal("0"))),
            "formatter": _amount_formatter,
            "icon": "🏭",
            "description": "本業による利益水準",
            "tone_fn": lambda v: "negative" if v < Decimal("0") else "positive" if v > Decimal("0") else "neutral",
        },
        "ord": {
            "label": "経常利益",
            "value": Decimal(amounts.get("ORD", Decimal("0"))),
            "formatter": _amount_formatter,
            "icon": "📊",
            "description": "営業外収支を含む利益",
            "tone_fn": lambda v: "negative" if v < Decimal("0") else "positive" if v > Decimal("0") else "neutral",
        },
        "operating_cf": {
            "label": "営業キャッシュフロー",
            "value": Decimal(cf_data.get("営業キャッシュフロー", Decimal("0"))),
            "formatter": _amount_formatter,
            "icon": "💡",
            "description": "営業活動で得たキャッシュ",
            "tone_fn": lambda v: "negative" if v < Decimal("0") else "positive" if v > Decimal("0") else "neutral",
        },
        "fcf": {
            "label": "フリーCF",
            "value": Decimal(cf_data.get("キャッシュ増減", Decimal("0"))),
            "formatter": _amount_formatter,
            "icon": "🪙",
            "description": "投資・財務CF後に残る現金",
            "tone_fn": lambda v: "negative" if v < Decimal("0") else "positive" if v > Decimal("0") else "neutral",
        },
        "net_income": {
            "label": "税引後利益",
            "value": Decimal(cf_data.get("税引後利益", Decimal("0"))),
            "formatter": _amount_formatter,
            "icon": "✅",
            "description": "法人税控除後の純利益",
            "tone_fn": lambda v: "negative" if v < Decimal("0") else "positive" if v > Decimal("0") else "neutral",
        },
        "cash": {
            "label": "期末現金残高",
            "value": Decimal(cash_total),
            "formatter": _amount_formatter,
            "icon": "💰",
            "description": "貸借対照表上の現金・預金残高",
            "tone_fn": lambda v: "negative" if v < Decimal("0") else "positive" if v > Decimal("0") else "neutral",
        },
        "equity_ratio": {
            "label": "自己資本比率",
            "value": Decimal(bs_metrics.get("equity_ratio", Decimal("NaN"))),
            "formatter": format_ratio,
            "icon": "🛡️",
            "description": "総資産に対する自己資本の割合",
            "tone_fn": lambda v: _tone_threshold(v, positive=Decimal("0.4"), caution=Decimal("0.2")),
        },
        "roe": {
            "label": "ROE",
            "value": Decimal(bs_metrics.get("roe", Decimal("NaN"))),
            "formatter": format_ratio,
            "icon": "📐",
            "description": "自己資本に対する利益率",
            "tone_fn": lambda v: _tone_threshold(v, positive=Decimal("0.1"), caution=Decimal("0.0")),
        },
        "working_capital": {
            "label": "ネット運転資本",
            "value": Decimal(bs_metrics.get("working_capital", Decimal("0"))),
            "formatter": _yen_formatter,
            "icon": "🔄",
            "description": "売掛金・棚卸資産と買掛金の差分",
        },
        "customer_count": {
            "label": "年間想定顧客数",
            "value": Decimal(sales_summary.get("total_customers", Decimal("0"))),
            "formatter": _count_formatter,
            "icon": "🙋",
            "description": "年間に購買する顧客数の見込み",
        },
        "avg_unit_price": {
            "label": "平均客単価",
            "value": Decimal(sales_summary.get("avg_unit_price", Decimal("0"))),
            "formatter": _yen_formatter,
            "icon": "🏷️",
            "description": "取引1件当たりの平均売上",
        },
        "avg_frequency": {
            "label": "平均購入頻度/月",
            "value": Decimal(sales_summary.get("avg_frequency", Decimal("0"))),
            "formatter": _frequency_formatter,
            "icon": "🔁",
            "description": "顧客1人当たりの月間購買頻度",
        },
    }

    if "custom_kpi_selection" not in st.session_state:
        base_default = ["sales", "gross", "op", "operating_cf"]
        suggestion_map = {"customers": "customer_count", "unit_price": "avg_unit_price", "frequency": "avg_frequency"}
        suggestions: List[str] = []
        template_metrics = industry_metric_state.get(industry_template_key, {})
        for cfg in template_metrics.values():
            metric_type = str(cfg.get("type", ""))
            mapped = suggestion_map.get(metric_type)
            if mapped and mapped not in suggestions and mapped in kpi_options:
                suggestions.append(mapped)
        st.session_state["custom_kpi_selection"] = list(dict.fromkeys(base_default + suggestions))

    with st.expander("カードをカスタマイズ", expanded=False):
        current_selection = st.session_state.get("custom_kpi_selection", [])
        selection = st.multiselect(
            "表示するKPIカード",
            list(kpi_options.keys()),
            default=current_selection,
            format_func=lambda key: str(kpi_options[key]["label"]),
        )
        if selection:
            st.session_state["custom_kpi_selection"] = selection

    selected_keys = st.session_state.get("custom_kpi_selection", [])
    if not selected_keys:
        selected_keys = ["sales"]

    cards: List[MetricCard] = []
    for key in selected_keys:
        cfg = kpi_options.get(key)
        if not cfg:
            continue
        raw_value = Decimal(cfg.get("value", Decimal("0")))
        formatter = cfg.get("formatter", _amount_formatter)
        formatted_value = formatter(raw_value) if callable(formatter) else str(raw_value)
        tone_fn = cfg.get("tone_fn")
        tone = tone_fn(raw_value) if callable(tone_fn) else None
        descriptor = str(cfg.get("description", ""))
        assistive_text = (
            f"{cfg.get('label')}のカード。{descriptor}" if descriptor else f"{cfg.get('label')}のカード。"
        )
        cards.append(
            MetricCard(
                icon=str(cfg.get("icon", "📊")),
                label=str(cfg.get("label")),
                value=str(formatted_value),
                description=descriptor,
                aria_label=f"{cfg.get('label')} {formatted_value}",
                tone=tone,
                assistive_text=assistive_text,
            )
        )

    if cards:
        render_metric_cards(cards, grid_aria_label="カスタムKPI")

    st.caption(
        f"運転資本想定: 売掛 {bs_metrics.get('receivable_days', Decimal('0'))}日 / "
        f"棚卸 {bs_metrics.get('inventory_days', Decimal('0'))}日 / "
        f"買掛 {bs_metrics.get('payable_days', Decimal('0'))}日"
    )

    range_entries = [
        ("売上高", sales_range_min, sales_range_typical, sales_range_max),
        ("変動費", variable_cost_range.minimum, variable_cost_range.typical, variable_cost_range.maximum),
        ("固定費", fixed_cost_range.minimum, fixed_cost_range.typical, fixed_cost_range.maximum),
        (
            "営業外",
            non_operating_range.minimum,
            non_operating_range.typical,
            non_operating_range.maximum,
        ),
    ]
    range_entries = [
        entry for entry in range_entries if any(value > Decimal("0") for value in entry[1:])
    ]
    if range_entries:
        st.markdown("#### 推定レンジの可視化")
        range_fig = go.Figure()
        for idx, (label, minimum, typical, maximum) in enumerate(range_entries):
            upper = float((maximum - typical) / unit_factor) if maximum > typical else 0.0
            lower = float((typical - minimum) / unit_factor) if typical > minimum else 0.0
            range_fig.add_trace(
                go.Bar(
                    name=label,
                    x=[label],
                    y=[float(typical / unit_factor)],
                    marker=dict(color=palette[idx % len(palette)]),
                    error_y=dict(type="data", array=[upper], arrayminus=[lower], visible=True),
                )
            )
        range_fig.update_layout(
            template="plotly_white",
            showlegend=False,
            title="中央値と上下レンジ",
            yaxis_title=f"金額 ({unit})",
        )
        st.plotly_chart(
            range_fig,
            use_container_width=True,
            config=plotly_download_config("estimate_ranges"),
        )

        range_table = pd.DataFrame(
            {
                "項目": [label for label, *_ in range_entries],
                "最低": [format_amount_with_unit(minimum, unit) for _, minimum, _, _ in range_entries],
                "中央値": [
                    format_amount_with_unit(typical, unit) for _, _, typical, _ in range_entries
                ],
                "最高": [format_amount_with_unit(maximum, unit) for _, _, _, maximum in range_entries],
            }
        )
        st.dataframe(range_table, hide_index=True, use_container_width=True)
        st.caption("レンジはFermi推定およびレンジ入力値を基に算出しています。")

    financial_cards = [
        MetricCard(
            icon="📊",
            label="粗利率",
            value=format_ratio(metrics.get("gross_margin")),
            description="粗利÷売上",
            tone="positive" if _to_decimal(metrics.get("gross_margin", Decimal("0"))) >= Decimal("0.3") else "caution",
            aria_label="粗利率",
            assistive_text="粗利率のカード。粗利÷売上で収益性を確認できます。",
        ),
        MetricCard(
            icon="💼",
            label="営業利益率",
            value=format_ratio(metrics.get("op_margin")),
            description="営業利益÷売上",
            tone="positive" if _to_decimal(metrics.get("op_margin", Decimal("0"))) >= Decimal("0.1") else "caution",
            aria_label="営業利益率",
            assistive_text="営業利益率のカード。販管費や投資負担を踏まえた収益性を示します。",
        ),
        MetricCard(
            icon="📈",
            label="経常利益率",
            value=format_ratio(metrics.get("ord_margin")),
            description="経常利益÷売上",
            tone="positive" if _to_decimal(metrics.get("ord_margin", Decimal("0"))) >= Decimal("0.08") else "caution",
            aria_label="経常利益率",
            assistive_text="経常利益率のカード。金融収支を含む最終的な収益力を示します。",
        ),
        MetricCard(
            icon="🛡️",
            label="自己資本比率",
            value=format_ratio(bs_metrics.get("equity_ratio", Decimal("NaN"))),
            description="総資産に対する自己資本",
            tone=_tone_threshold(
                _to_decimal(bs_metrics.get("equity_ratio", Decimal("0"))),
                positive=Decimal("0.4"),
                caution=Decimal("0.2"),
            ),
            aria_label="自己資本比率",
            assistive_text="自己資本比率のカード。財務の安定性を示し、40%超で健全域です。",
        ),
        MetricCard(
            icon="🎯",
            label="ROE",
            value=format_ratio(bs_metrics.get("roe", Decimal("NaN"))),
            description="自己資本利益率",
            tone=_tone_threshold(
                _to_decimal(bs_metrics.get("roe", Decimal("0"))),
                positive=Decimal("0.1"),
                caution=Decimal("0.0"),
            ),
            aria_label="ROE",
            assistive_text="ROEのカード。自己資本に対する利益創出力を示します。",
        ),
    ]
    render_metric_cards(financial_cards, grid_aria_label="財務KPIサマリー")

    monthly_pl_fig = go.Figure()
    monthly_pl_fig.add_trace(
        go.Bar(
            name='売上原価',
            x=monthly_pl_df['month'],
            y=monthly_pl_df['売上原価'],
            marker=dict(
                color=palette[1],
                pattern=dict(shape='/', fgcolor='rgba(0,0,0,0.15)'),
            ),
            hovertemplate='月=%{x}<br>売上原価=¥%{y:,.0f}<extra></extra>',
        )
    )
    monthly_pl_fig.add_trace(
        go.Bar(
            name='販管費',
            x=monthly_pl_df['month'],
            y=monthly_pl_df['販管費'],
            marker=dict(
                color=palette[3],
                pattern=dict(shape='x', fgcolor='rgba(0,0,0,0.15)'),
            ),
            hovertemplate='月=%{x}<br>販管費=¥%{y:,.0f}<extra></extra>',
        )
    )
    monthly_pl_fig.add_trace(
        go.Bar(
            name='営業利益',
            x=monthly_pl_df['month'],
            y=monthly_pl_df['営業利益'],
            marker=dict(
                color=palette[2],
                pattern=dict(shape='.', fgcolor='rgba(0,0,0,0.12)'),
            ),
            hovertemplate='月=%{x}<br>営業利益=¥%{y:,.0f}<extra></extra>',
        )
    )
    monthly_pl_fig.add_trace(
        go.Scatter(
            name='売上高',
            x=monthly_pl_df['month'],
            y=monthly_pl_df['売上高'],
            mode='lines+markers',
            line=dict(color=palette[0], width=3),
            marker=dict(symbol='diamond-open', size=8, line=dict(color=palette[0], width=2)),
            hovertemplate='月=%{x}<br>売上高=¥%{y:,.0f}<extra></extra>',
        )
    )
    monthly_pl_fig.update_layout(
        barmode='stack',
        hovermode='x unified',
        legend=dict(
            title=dict(text=''),
            itemclick='toggleothers',
            itemdoubleclick='toggle',
            orientation='h',
            y=-0.18,
        ),
        yaxis_title='金額 (円)',
        yaxis_tickformat=',',
    )

    st.markdown('### 月次PL（スタック棒）')
    st.plotly_chart(
        monthly_pl_fig,
        use_container_width=True,
        config=plotly_download_config('monthly_pl'),
    )
    st.caption("パターン付きの棒グラフで色の違いが分かりにくい場合でも区別できます。")

    trend_cols = st.columns(2)
    with trend_cols[0]:
        margin_fig = go.Figure()
        margin_fig.add_trace(
            go.Scatter(
                x=monthly_pl_df['month'],
                y=(monthly_pl_df['粗利率'] * 100).round(4),
                mode='lines+markers',
                name='粗利率',
                line=dict(color=palette[4], width=3),
                marker=dict(symbol='circle', size=8, line=dict(width=1.5, color=palette[4])),
                hovertemplate='月=%{x}<br>粗利率=%{y:.1f}%<extra></extra>',
            )
        )
        margin_fig.update_layout(
            hovermode='x unified',
            yaxis_title='粗利率 (%)',
            yaxis_ticksuffix='%',
            yaxis_tickformat='.1f',
            legend=dict(
                title=dict(text=''), itemclick='toggleothers', itemdoubleclick='toggle'
            ),
        )
        margin_fig.update_yaxes(gridcolor='rgba(31, 78, 121, 0.15)', zerolinecolor='rgba(31, 78, 121, 0.3)')
        st.markdown('#### 粗利率推移')
        st.plotly_chart(
            margin_fig,
            use_container_width=True,
            config=plotly_download_config('gross_margin_trend'),
        )

    with trend_cols[1]:
        st.markdown('#### 費用構成ドーナツ')
        if not cost_df.empty:
            cost_fig = go.Figure(
                go.Pie(
                    labels=cost_df['項目'],
                    values=cost_df['金額'],
                    hole=0.55,
                    textinfo='label+percent',
                    hovertemplate='%{label}: ¥%{value:,.0f}<extra></extra>',
                    marker=dict(
                        colors=palette[: len(cost_df)],
                        line=dict(color='#FFFFFF', width=1.5),
                    ),
                )
            )
            cost_fig.update_layout(
                legend=dict(
                    title=dict(text=''), itemclick='toggleothers', itemdoubleclick='toggle'
                )
            )
            st.plotly_chart(
                cost_fig,
                use_container_width=True,
                config=plotly_download_config('cost_breakdown'),
            )
        else:
            st.info('費用構成を表示するデータがありません。')

    st.markdown('### FCFウォーターフォール')
    fcf_labels = [step['name'] for step in fcf_steps]
    fcf_values = [step['value'] for step in fcf_steps]
    fcf_measures = ['relative'] * (len(fcf_values) - 1) + ['total']
    fcf_fig = go.Figure(
        go.Waterfall(
            name='FCF',
            orientation='v',
            measure=fcf_measures,
            x=fcf_labels,
            y=fcf_values,
            text=[f"¥{value:,.0f}" for value in fcf_values],
            hovertemplate='%{x}: ¥%{y:,.0f}<extra></extra>',
            connector=dict(line=dict(color=THEME_COLORS["neutral"], dash='dot')),
            increasing=dict(marker=dict(color=palette[2])),
            decreasing=dict(marker=dict(color=THEME_COLORS["negative"])),
            totals=dict(marker=dict(color=THEME_COLORS["primary"])),
        )
    )
    fcf_fig.update_layout(
        showlegend=False,
        yaxis_title='金額 (円)',
        yaxis_tickformat=',',
    )
st.plotly_chart(
    fcf_fig,
    use_container_width=True,
    config=plotly_download_config('fcf_waterfall'),
)

investment_metrics = cf_data.get("investment_metrics", {})
if isinstance(investment_metrics, dict) and investment_metrics.get("monthly_cash_flows"):
    st.markdown('### 投資評価指標')
    payback_years_value = investment_metrics.get("payback_period_years")
    npv_value = Decimal(str(investment_metrics.get("npv", Decimal("0"))))
    discount_rate_value = Decimal(
        str(investment_metrics.get("discount_rate", Decimal("0")))
    )

    metric_cols = st.columns(3)
    with metric_cols[0]:
        if payback_years_value is None:
            payback_text = "—"
        else:
            payback_decimal = Decimal(str(payback_years_value))
            payback_text = f"{float(payback_decimal):.1f}年"
        st.metric("投資回収期間", payback_text)
    with metric_cols[1]:
        st.metric("NPV (現在価値)", format_amount_with_unit(npv_value, "円"))
    with metric_cols[2]:
        st.metric("割引率", f"{float(discount_rate_value) * 100:.1f}%")

    with st.expander("月次キャッシュフロー予測", expanded=False):
        projection_rows = []
        for entry in investment_metrics.get("monthly_cash_flows", []):
            projection_rows.append(
                {
                    "月": f"FY{int(entry['year'])} 月{int(entry['month']):02d}",
                    "営業CF(利払前)": float(entry["operating"]),
                    "投資CF": float(entry["investing"]),
                    "財務CF": float(entry["financing"]),
                    "ネット": float(entry["net"]),
                    "累計": float(entry["cumulative"]),
                }
            )
        projection_df = pd.DataFrame(projection_rows)
        st.dataframe(
            projection_df,
            hide_index=True,
            **use_container_width_kwargs(st.dataframe),
        )

capex_schedule_data = cf_data.get("capex_schedule", [])
loan_schedule_data = cf_data.get("loan_schedule", [])
if capex_schedule_data or loan_schedule_data:
    st.markdown('### 投資・借入スケジュール')
    schedule_cols = st.columns(2)
    with schedule_cols[0]:
        st.markdown('#### 設備投資支払')
        if capex_schedule_data:
            capex_rows = [
                {
                    '投資名': entry.get('name', ''),
                    '時期': f"FY{int(entry.get('year', 1))} 月{int(entry.get('month', 1)):02d}",
                    '支払額': format_amount_with_unit(Decimal(str(entry.get('amount', 0))), '円'),
                }
                for entry in capex_schedule_data
            ]
            capex_df_display = pd.DataFrame(capex_rows)
            st.dataframe(
                capex_df_display,
                hide_index=True,
                **use_container_width_kwargs(st.dataframe),
            )
        else:
            st.info('表示する設備投資スケジュールがありません。')
    with schedule_cols[1]:
        st.markdown('#### 借入返済（年次サマリー）')
        if loan_schedule_data:
            aggregated: Dict[int, Dict[str, Decimal]] = {}
            for entry in loan_schedule_data:
                year_key = int(entry.get('year', 1))
                data = aggregated.setdefault(
                    year_key,
                    {'interest': Decimal('0'), 'principal': Decimal('0')},
                )
                data['interest'] += Decimal(str(entry.get('interest', 0)))
                data['principal'] += Decimal(str(entry.get('principal', 0)))
            summary_rows = [
                {
                    '年度': f"FY{year}",
                    '利息': format_amount_with_unit(values['interest'], '円'),
                    '元金': format_amount_with_unit(values['principal'], '円'),
                    '返済額合計': format_amount_with_unit(
                        values['interest'] + values['principal'], '円'
                    ),
                }
                for year, values in sorted(aggregated.items())
            ]
            summary_df = pd.DataFrame(summary_rows)
            st.dataframe(
                summary_df,
                hide_index=True,
                **use_container_width_kwargs(st.dataframe),
            )

            with st.expander('月次内訳を見る', expanded=False):
                monthly_rows = [
                    {
                        'ローン': entry.get('loan_name', ''),
                        '時期': f"FY{int(entry.get('year', 1))} 月{int(entry.get('month', 1)):02d}",
                        '利息': float(Decimal(str(entry.get('interest', 0)))),
                        '元金': float(Decimal(str(entry.get('principal', 0)))),
                        '残高': float(Decimal(str(entry.get('balance', 0)))),
                    }
                    for entry in loan_schedule_data
                ]
                loan_monthly_df = pd.DataFrame(monthly_rows)
                st.dataframe(
                    loan_monthly_df,
                    hide_index=True,
                    **use_container_width_kwargs(st.dataframe),
                )
        else:
            st.info('借入返済スケジュールが未設定です。')

    st.markdown('### 月次キャッシュフローと累計キャッシュ')
    if not monthly_cf_df.empty:
        cf_fig = go.Figure()
        cf_fig.add_trace(
            go.Bar(
                name='営業CF',
                x=monthly_cf_df['月'],
                y=monthly_cf_df['営業CF'],
                marker=dict(
                    color=palette[2],
                    pattern=dict(shape='/', fgcolor='rgba(0,0,0,0.15)'),
                ),
                hovertemplate='月=%{x}<br>営業CF=¥%{y:,.0f}<extra></extra>',
            )
        )
        cf_fig.add_trace(
            go.Bar(
                name='投資CF',
                x=monthly_cf_df['月'],
                y=monthly_cf_df['投資CF'],
                marker=dict(
                    color=THEME_COLORS['negative'],
                    pattern=dict(shape='x', fgcolor='rgba(0,0,0,0.2)'),
                ),
                hovertemplate='月=%{x}<br>投資CF=¥%{y:,.0f}<extra></extra>',
            )
        )
        cf_fig.add_trace(
            go.Bar(
                name='財務CF',
                x=monthly_cf_df['月'],
                y=monthly_cf_df['財務CF'],
                marker=dict(
                    color=palette[0],
                    pattern=dict(shape='\\', fgcolor='rgba(0,0,0,0.15)'),
                ),
                hovertemplate='月=%{x}<br>財務CF=¥%{y:,.0f}<extra></extra>',
            )
        )
        cf_fig.add_trace(
            go.Scatter(
                name='累計キャッシュ',
                x=monthly_cf_df['月'],
                y=monthly_cf_df['累計キャッシュ'],
                mode='lines+markers',
                line=dict(color=palette[5], width=3),
                marker=dict(symbol='triangle-up', size=8, line=dict(color=palette[5], width=1.5)),
                hovertemplate='月=%{x}<br>累計=¥%{y:,.0f}<extra></extra>',
                yaxis='y2',
            )
        )
        cf_fig.update_layout(
            barmode='relative',
            hovermode='x unified',
            yaxis=dict(title='金額 (円)', tickformat=','),
            yaxis2=dict(
                title='累計キャッシュ (円)',
                overlaying='y',
                side='right',
                tickformat=',',
            ),
            legend=dict(
                title=dict(text=''),
                itemclick='toggleothers',
                itemdoubleclick='toggle',
                orientation='h',
                yanchor='bottom',
                y=1.02,
                x=0,
                bgcolor='rgba(255,255,255,0.6)',
            ),
        )
        st.plotly_chart(cf_fig, use_container_width=True, config=plotly_download_config('monthly_cf'))
        st.caption("各キャッシュフローは模様と形状で識別できます。")
        st.dataframe(
            monthly_cf_df,
            hide_index=True,
            **use_container_width_kwargs(st.dataframe),
        )
    else:
        st.info('月次キャッシュフローを表示するデータがありません。')

    st.markdown('### 月次バランスシート')
    if not monthly_bs_df.empty:
        st.dataframe(
            monthly_bs_df,
            hide_index=True,
            **use_container_width_kwargs(st.dataframe),
        )
    else:
        st.info('月次バランスシートを表示するデータがありません。')

    st.markdown('### PLサマリー')
    pl_rows: List[Dict[str, object]] = []
    for code, label, group in ITEMS:
        if code in {'BE_SALES', 'PC_SALES', 'PC_GROSS', 'PC_ORD', 'LDR'}:
            continue
        value = amounts.get(code, Decimal('0'))
        pl_rows.append({'カテゴリ': group, '項目': label, '金額': float(value)})
    pl_df = pd.DataFrame(pl_rows)
    st.dataframe(
        pl_df,
        hide_index=True,
        **use_container_width_kwargs(st.dataframe),
    )

    if external_actuals:
        st.markdown('### 予実差異分析')
        actual_sales_map = external_actuals.get('sales', {}).get('monthly', {})
        actual_variable_map = external_actuals.get('variable_costs', {}).get('monthly', {})
        actual_fixed_map = external_actuals.get('fixed_costs', {}).get('monthly', {})

        actual_sales_total = sum((Decimal(str(v)) for v in actual_sales_map.values()), start=Decimal('0'))
        actual_variable_total = sum((Decimal(str(v)) for v in actual_variable_map.values()), start=Decimal('0'))
        actual_fixed_total = sum((Decimal(str(v)) for v in actual_fixed_map.values()), start=Decimal('0'))

        plan_sales_total = Decimal(amounts.get('REV', Decimal('0')))
        plan_gross_total = Decimal(amounts.get('GROSS', Decimal('0')))
        plan_variable_total = Decimal(amounts.get('COGS_TTL', Decimal('0')))
        plan_fixed_total = Decimal(amounts.get('OPEX_TTL', Decimal('0')))
        plan_op_total = Decimal(amounts.get('OP', Decimal('0')))

        actual_gross_total = actual_sales_total - actual_variable_total
        actual_op_total = actual_gross_total - actual_fixed_total

        variance_rows = [
            {
                '項目': '売上高',
                '予算': plan_sales_total,
                '実績': actual_sales_total,
                '差異': actual_sales_total - plan_sales_total,
            },
            {
                '項目': '粗利',
                '予算': plan_gross_total,
                '実績': actual_gross_total,
                '差異': actual_gross_total - plan_gross_total,
            },
            {
                '項目': '営業利益',
                '予算': plan_op_total,
                '実績': actual_op_total,
                '差異': actual_op_total - plan_op_total,
            },
        ]

        formatted_rows: List[Dict[str, str]] = []
        for row in variance_rows:
            plan_val = row['予算']
            actual_val = row['実績']
            diff_val = row['差異']
            variance_ratio = diff_val / plan_val if plan_val not in (Decimal('0'), Decimal('NaN')) else Decimal('NaN')
            formatted_rows.append(
                {
                    '項目': row['項目'],
                    '予算': format_amount_with_unit(plan_val, unit),
                    '実績': format_amount_with_unit(actual_val, unit),
                    '差異': format_amount_with_unit(diff_val, unit),
                    '差異率': format_ratio(variance_ratio),
                }
            )
        variance_display_df = pd.DataFrame(formatted_rows)
        st.dataframe(
            variance_display_df,
            hide_index=True,
            **use_container_width_kwargs(st.dataframe),
        )

        sales_diff = actual_sales_total - plan_sales_total
        sales_diff_ratio = sales_diff / plan_sales_total if plan_sales_total else Decimal('NaN')
        act_lines: List[str] = []
        if plan_sales_total > 0:
            if sales_diff < 0:
                act_lines.append('売上が計画を下回っているため、チャネル別の客数と単価前提を再確認し販促計画を見直しましょう。')
            else:
                act_lines.append('売上が計画を上回っています。好調チャネルへの投資増や在庫確保を検討できます。')
        if actual_variable_total > plan_variable_total:
            act_lines.append('原価率が悪化しているため、仕入条件や値上げ余地を検証してください。')
        if actual_fixed_total > plan_fixed_total:
            act_lines.append('固定費が計画を超過しています。人件費や販管費の効率化施策を検討しましょう。')
        if not act_lines:
            act_lines.append('計画に対して大きな乖離はありません。現状の施策を継続しつつ改善余地を探索しましょう。')

        st.markdown('#### PDCAサマリー')
        plan_text = format_amount_with_unit(plan_sales_total, unit)
        plan_op_text = format_amount_with_unit(plan_op_total, unit)
        actual_text = format_amount_with_unit(actual_sales_total, unit)
        actual_op_text = format_amount_with_unit(actual_op_total, unit)
        sales_diff_text = format_amount_with_unit(sales_diff, unit)
        sales_diff_ratio_text = format_ratio(sales_diff_ratio)
        act_html = ''.join(f'- {line}<br/>' for line in act_lines)
        st.markdown(
            f"- **Plan:** 売上 {plan_text} / 営業利益 {plan_op_text}<br/>"
            f"- **Do:** 実績 売上 {actual_text} / 営業利益 {actual_op_text}<br/>"
            f"- **Check:** 売上差異 {sales_diff_text} ({sales_diff_ratio_text})<br/>"
            f"- **Act:**<br/>{act_html}",
            unsafe_allow_html=True,
        )

with be_tab:
    st.subheader("損益分岐点分析")
    be_sales = metrics.get("breakeven", Decimal("0"))
    sales = amounts.get("REV", Decimal("0"))
    if isinstance(be_sales, Decimal) and be_sales.is_finite() and sales > 0:
        ratio = be_sales / sales
    else:
        ratio = Decimal("0")
    safety_margin = Decimal("1") - ratio if sales > 0 else Decimal("0")

    info_cols = st.columns(3)
    info_cols[0].metric("損益分岐点売上高", format_amount_with_unit(be_sales, unit))
    info_cols[1].metric("現在の売上高", format_amount_with_unit(sales, unit))
    info_cols[2].metric("安全余裕度", format_ratio(safety_margin))

    st.progress(min(max(float(safety_margin), 0.0), 1.0), "安全余裕度")
    st.caption("進捗バーは売上高が損益分岐点をどの程度上回っているかを可視化します。")

    cvp_fig = go.Figure()
    cvp_fig.add_trace(
        go.Scatter(
            name='売上線',
            x=cvp_df['売上高'],
            y=cvp_df['売上高'],
            mode='lines',
            line=dict(color='#636EFA'),
            hovertemplate='売上高=¥%{x:,.0f}<extra></extra>',
        )
    )
    cvp_fig.add_trace(
        go.Scatter(
            name='総費用線',
            x=cvp_df['売上高'],
            y=cvp_df['総費用'],
            mode='lines',
            line=dict(color='#EF553B'),
            hovertemplate='売上高=¥%{x:,.0f}<br>総費用=¥%{y:,.0f}<extra></extra>',
        )
    )
    if isinstance(breakeven_sales, Decimal) and breakeven_sales.is_finite() and breakeven_sales > 0:
        be_value = float(breakeven_sales)
        cvp_fig.add_trace(
            go.Scatter(
                name='損益分岐点',
                x=[be_value],
                y=[be_value],
                mode='markers',
                marker=dict(color='#00CC96', size=12, symbol='diamond'),
                hovertemplate='損益分岐点=¥%{x:,.0f}<extra></extra>',
            )
        )
    cvp_fig.update_layout(
        xaxis_title='売上高 (円)',
        yaxis_title='金額 (円)',
        hovermode='x unified',
        legend=dict(title=dict(text=''), itemclick='toggleothers', itemdoubleclick='toggle'),
        xaxis_tickformat=',',
        yaxis_tickformat=',',
    )

    st.markdown('### CVPチャート')
    st.plotly_chart(
        cvp_fig,
        use_container_width=True,
        config=plotly_download_config('cvp_chart'),
    )
    st.caption(
        f"変動費率: {format_ratio(variable_rate)} ／ 固定費: {format_amount_with_unit(fixed_cost, unit)}"
    )

    st.markdown("### バランスシートのスナップショット")
    bs_rows = []
    for section, records in (("資産", bs_data["assets"]), ("負債・純資産", bs_data["liabilities"])):
        for name, value in records.items():
            bs_rows.append({"区分": section, "項目": name, "金額": float(value)})
    bs_df = pd.DataFrame(bs_rows)
    st.dataframe(
        bs_df,
        hide_index=True,
        **use_container_width_kwargs(st.dataframe),
    )

with cash_tab:
    st.subheader("キャッシュフロー")
    cf_rows = [{"区分": key, "金額": float(value)} for key, value in cf_data.items()]
    cf_df = pd.DataFrame(cf_rows)
    st.dataframe(
        cf_df,
        hide_index=True,
        **use_container_width_kwargs(st.dataframe),
    )

    cf_fig = go.Figure(
        go.Bar(
            x=cf_df['区分'],
            y=cf_df['金額'],
            marker_color='#636EFA',
            hovertemplate='%{x}: ¥%{y:,.0f}<extra></extra>',
        )
    )
    cf_fig.update_layout(
        showlegend=False,
        yaxis_title='金額 (円)',
        yaxis_tickformat=',',
    )
    st.plotly_chart(
        cf_fig,
        use_container_width=True,
        config=plotly_download_config('cashflow_summary'),
    )

    st.markdown('### DSCR / 債務償還年数')
    if not dscr_df.empty:
        dscr_fig = make_subplots(specs=[[{'secondary_y': True}]])
        dscr_fig.add_trace(
            go.Scatter(
                x=dscr_df['年度'],
                y=dscr_df['DSCR'],
                name='DSCR',
                mode='lines+markers',
                line=dict(color='#636EFA'),
                hovertemplate='%{x}: %{y:.2f}x<extra></extra>',
            ),
            secondary_y=False,
        )
        dscr_fig.add_trace(
            go.Scatter(
                x=dscr_df['年度'],
                y=dscr_df['債務償還年数'],
                name='債務償還年数',
                mode='lines+markers',
                line=dict(color='#EF553B'),
                hovertemplate='%{x}: %{y:.1f}年<extra></extra>',
            ),
            secondary_y=True,
        )
        dscr_fig.update_yaxes(title_text='DSCR (倍)', tickformat='.2f', secondary_y=False)
        dscr_fig.update_yaxes(
            title_text='債務償還年数 (年)', tickformat='.1f', secondary_y=True
        )
        dscr_fig.update_layout(
            hovermode='x unified',
            legend=dict(
                title=dict(text=''), itemclick='toggleothers', itemdoubleclick='toggle'
            ),
        )
        st.plotly_chart(
            dscr_fig,
            use_container_width=True,
            config=plotly_download_config('dscr_timeseries'),
        )
    else:
        st.info('借入データが未登録のため、DSCRを算出できません。')

    st.caption("営業CFには減価償却費を足し戻し、税引後利益を反映しています。投資CFはCapex、財務CFは利息支払を表します。")
