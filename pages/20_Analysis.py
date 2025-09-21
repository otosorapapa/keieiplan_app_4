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
from formatting import format_amount_with_unit, format_ratio
from state import ensure_session_defaults, load_finance_bundle
from models import INDUSTRY_TEMPLATES, CapexPlan, LoanSchedule
from theme import inject_theme

ITEM_LABELS = {code: label for code, label, _ in ITEMS}

PLOTLY_DOWNLOAD_OPTIONS = {
    "format": "png",
    "height": 600,
    "width": 1000,
    "scale": 2,
}


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
        "OPEX_K",
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
    for item in capex.items:
        month = int(getattr(item, "start_month", 1))
        month = max(1, min(12, month))
        schedule[month] += Decimal(item.amount)
    return schedule


def _monthly_interest_schedule(loans: LoanSchedule) -> Dict[int, Decimal]:
    schedule = {month: Decimal("0") for month in range(1, 13)}
    for loan in loans.loans:
        principal = Decimal(loan.principal)
        rate = Decimal(loan.interest_rate)
        term_months = int(loan.term_months)
        start_month = int(loan.start_month)
        outstanding = principal
        for offset in range(term_months):
            month_index = start_month + offset
            interest = outstanding * rate / Decimal("12")
            if 1 <= month_index <= 12:
                schedule[month_index] += interest
            if loan.repayment_type == "equal_principal":
                principal_payment = principal / Decimal(term_months)
            else:
                principal_payment = principal if offset == term_months - 1 else Decimal("0")
            principal_payment = min(principal_payment, outstanding)
            outstanding = max(Decimal("0"), outstanding - principal_payment)
            if month_index >= 12:
                break
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
    records: List[Dict[str, object]] = []
    for loan in loans_data.get("loans", []):
        principal = _to_decimal(loan.get("principal", "0"))
        rate = _to_decimal(loan.get("interest_rate", "0"))
        term_months = int(loan.get("term_months", 0))
        start_month = int(loan.get("start_month", 1))
        repayment_type = str(loan.get("repayment_type", "equal_principal"))
        if term_months <= 0 or principal <= 0:
            continue
        outstanding = principal
        for offset in range(term_months):
            month_index = start_month + offset
            year_index = (month_index - 1) // 12 + 1
            interest = outstanding * rate / Decimal("12")
            if repayment_type == "equal_principal":
                principal_payment = principal / Decimal(term_months)
            else:
                principal_payment = principal if offset == term_months - 1 else Decimal("0")
            principal_payment = min(principal_payment, outstanding)
            ending = outstanding - principal_payment
            records.append(
                {
                    "year": year_index,
                    "interest": interest,
                    "principal": principal_payment,
                    "out_start": outstanding,
                    "out_end": ending,
                }
            )
            outstanding = ending

    if not records:
        return pd.DataFrame()

    grouped_rows: List[Dict[str, float]] = []
    for year, group in pd.DataFrame(records).groupby("year"):
        interest_total = sum(group["interest"], start=Decimal("0"))
        principal_total = sum(group["principal"], start=Decimal("0"))
        outstanding_start = group["out_start"].iloc[0]
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
interest_schedule = _monthly_interest_schedule(bundle.loans)

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
monthly_noi = non_operating_income_total / Decimal("12") if non_operating_income_total else Decimal("0")
monthly_noe = non_operating_expense_total / Decimal("12") if non_operating_expense_total else Decimal("0")
tax_rate = Decimal(bundle.tax.corporate_tax_rate)

monthly_cf_entries: List[Dict[str, Decimal]] = []
running_cash = Decimal("0")
for idx, row in monthly_pl_df.iterrows():
    month_index = idx + 1
    operating_profit = Decimal(str(row["営業利益"]))
    ordinary_income_month = operating_profit + monthly_noi - monthly_noe
    taxes_month = ordinary_income_month * tax_rate if ordinary_income_month > 0 else Decimal("0")
    operating_cf_month = ordinary_income_month + monthly_depreciation - taxes_month
    investing_cf_month = -capex_schedule.get(month_index, Decimal("0"))
    financing_cf_month = -interest_schedule.get(month_index, Decimal("0"))
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

    kpi_options: Dict[str, Dict[str, object]] = {
        "sales": {
            "label": "売上高",
            "value": Decimal(amounts.get("REV", Decimal("0"))),
            "formatter": _amount_formatter,
        },
        "gross": {
            "label": "粗利",
            "value": Decimal(amounts.get("GROSS", Decimal("0"))),
            "formatter": _amount_formatter,
        },
        "op": {
            "label": "営業利益",
            "value": Decimal(amounts.get("OP", Decimal("0"))),
            "formatter": _amount_formatter,
        },
        "ord": {
            "label": "経常利益",
            "value": Decimal(amounts.get("ORD", Decimal("0"))),
            "formatter": _amount_formatter,
        },
        "operating_cf": {
            "label": "営業キャッシュフロー",
            "value": Decimal(cf_data.get("営業キャッシュフロー", Decimal("0"))),
            "formatter": _amount_formatter,
        },
        "fcf": {
            "label": "フリーCF",
            "value": Decimal(cf_data.get("キャッシュ増減", Decimal("0"))),
            "formatter": _amount_formatter,
        },
        "net_income": {
            "label": "税引後利益",
            "value": Decimal(cf_data.get("税引後利益", Decimal("0"))),
            "formatter": _amount_formatter,
        },
        "cash": {
            "label": "期末現金残高",
            "value": Decimal(cash_total),
            "formatter": _amount_formatter,
        },
        "equity_ratio": {
            "label": "自己資本比率",
            "value": Decimal(bs_metrics.get("equity_ratio", Decimal("NaN"))),
            "formatter": format_ratio,
        },
        "roe": {
            "label": "ROE",
            "value": Decimal(bs_metrics.get("roe", Decimal("NaN"))),
            "formatter": format_ratio,
        },
        "working_capital": {
            "label": "ネット運転資本",
            "value": Decimal(bs_metrics.get("working_capital", Decimal("0"))),
            "formatter": _yen_formatter,
        },
        "customer_count": {
            "label": "年間想定顧客数",
            "value": Decimal(sales_summary.get("total_customers", Decimal("0"))),
            "formatter": _count_formatter,
        },
        "avg_unit_price": {
            "label": "平均客単価",
            "value": Decimal(sales_summary.get("avg_unit_price", Decimal("0"))),
            "formatter": _yen_formatter,
        },
        "avg_frequency": {
            "label": "平均購入頻度/月",
            "value": Decimal(sales_summary.get("avg_frequency", Decimal("0"))),
            "formatter": _frequency_formatter,
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

    card_cols = st.columns(len(selected_keys))
    for col, key in zip(card_cols, selected_keys):
        cfg = kpi_options.get(key)
        if not cfg:
            continue
        raw_value = Decimal(cfg.get("value", Decimal("0")))
        formatter = cfg.get("formatter", _amount_formatter)
        if callable(formatter):
            formatted_value = formatter(raw_value)
        else:
            formatted_value = str(raw_value)
        col.metric(str(cfg.get("label")), formatted_value)

    st.caption(
        f"運転資本想定: 売掛 {bs_metrics.get('receivable_days', Decimal('0'))}日 / "
        f"棚卸 {bs_metrics.get('inventory_days', Decimal('0'))}日 / "
        f"買掛 {bs_metrics.get('payable_days', Decimal('0'))}日"
    )

    ratio_cols = st.columns(5)
    ratio_cols[0].metric("粗利率", format_ratio(metrics.get("gross_margin")))
    ratio_cols[1].metric("営業利益率", format_ratio(metrics.get("op_margin")))
    ratio_cols[2].metric("経常利益率", format_ratio(metrics.get("ord_margin")))
    ratio_cols[3].metric("自己資本比率", format_ratio(bs_metrics.get("equity_ratio", Decimal("NaN"))))
    ratio_cols[4].metric("ROE", format_ratio(bs_metrics.get("roe", Decimal("NaN"))))

    monthly_pl_fig = go.Figure()
    monthly_pl_fig.add_trace(
        go.Bar(
            name='売上原価',
            x=monthly_pl_df['month'],
            y=monthly_pl_df['売上原価'],
            marker_color='#FF9F43',
            hovertemplate='月=%{x}<br>売上原価=¥%{y:,.0f}<extra></extra>',
        )
    )
    monthly_pl_fig.add_trace(
        go.Bar(
            name='販管費',
            x=monthly_pl_df['month'],
            y=monthly_pl_df['販管費'],
            marker_color='#636EFA',
            hovertemplate='月=%{x}<br>販管費=¥%{y:,.0f}<extra></extra>',
        )
    )
    monthly_pl_fig.add_trace(
        go.Bar(
            name='営業利益',
            x=monthly_pl_df['month'],
            y=monthly_pl_df['営業利益'],
            marker_color='#00CC96',
            hovertemplate='月=%{x}<br>営業利益=¥%{y:,.0f}<extra></extra>',
        )
    )
    monthly_pl_fig.add_trace(
        go.Scatter(
            name='売上高',
            x=monthly_pl_df['month'],
            y=monthly_pl_df['売上高'],
            mode='lines+markers',
            line=dict(color='#EF553B', width=3),
            hovertemplate='月=%{x}<br>売上高=¥%{y:,.0f}<extra></extra>',
        )
    )
    monthly_pl_fig.update_layout(
        barmode='stack',
        hovermode='x unified',
        legend=dict(title=dict(text=''), itemclick='toggleothers', itemdoubleclick='toggle'),
        yaxis_title='金額 (円)',
        yaxis_tickformat=',',
    )

    st.markdown('### 月次PL（スタック棒）')
    st.plotly_chart(
        monthly_pl_fig,
        use_container_width=True,
        config=plotly_download_config('monthly_pl'),
    )

    trend_cols = st.columns(2)
    with trend_cols[0]:
        margin_fig = go.Figure()
        margin_fig.add_trace(
            go.Scatter(
                x=monthly_pl_df['month'],
                y=(monthly_pl_df['粗利率'] * 100).round(4),
                mode='lines+markers',
                name='粗利率',
                line=dict(color='#AB63FA'),
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

    st.markdown('### 月次キャッシュフローと累計キャッシュ')
    if not monthly_cf_df.empty:
        cf_fig = go.Figure()
        cf_fig.add_trace(
            go.Bar(
                name='営業CF',
                x=monthly_cf_df['月'],
                y=monthly_cf_df['営業CF'],
                marker_color='#00CC96',
                hovertemplate='月=%{x}<br>営業CF=¥%{y:,.0f}<extra></extra>',
            )
        )
        cf_fig.add_trace(
            go.Bar(
                name='投資CF',
                x=monthly_cf_df['月'],
                y=monthly_cf_df['投資CF'],
                marker_color='#EF553B',
                hovertemplate='月=%{x}<br>投資CF=¥%{y:,.0f}<extra></extra>',
            )
        )
        cf_fig.add_trace(
            go.Bar(
                name='財務CF',
                x=monthly_cf_df['月'],
                y=monthly_cf_df['財務CF'],
                marker_color='#636EFA',
                hovertemplate='月=%{x}<br>財務CF=¥%{y:,.0f}<extra></extra>',
            )
        )
        cf_fig.add_trace(
            go.Scatter(
                name='累計キャッシュ',
                x=monthly_cf_df['月'],
                y=monthly_cf_df['累計キャッシュ'],
                mode='lines+markers',
                line=dict(color='#FFA15A', width=3),
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
            legend=dict(title=dict(text=''), itemclick='toggleothers', itemdoubleclick='toggle'),
        )
        st.plotly_chart(cf_fig, use_container_width=True, config=plotly_download_config('monthly_cf'))
        st.dataframe(monthly_cf_df, use_container_width=True, hide_index=True)
    else:
        st.info('月次キャッシュフローを表示するデータがありません。')

    st.markdown('### 月次バランスシート')
    if not monthly_bs_df.empty:
        st.dataframe(monthly_bs_df, use_container_width=True, hide_index=True)
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
    st.dataframe(pl_df, use_container_width=True, hide_index=True)

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
        st.dataframe(variance_display_df, use_container_width=True, hide_index=True)

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
    st.dataframe(bs_df, use_container_width=True, hide_index=True)

with cash_tab:
    st.subheader("キャッシュフロー")
    cf_rows = [{"区分": key, "金額": float(value)} for key, value in cf_data.items()]
    cf_df = pd.DataFrame(cf_rows)
    st.dataframe(cf_df, use_container_width=True, hide_index=True)

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
