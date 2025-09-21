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
bs_data = generate_balance_sheet(amounts, bundle.capex, bundle.loans, bundle.tax)
cf_data = generate_cash_flow(amounts, bundle.capex, bundle.loans, bundle.tax)

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

st.title("📈 KPI・損益分析")
st.caption(f"FY{fiscal_year} / 表示単位: {unit} / FTE: {fte}")

kpi_tab, be_tab, cash_tab = st.tabs(["KPIダッシュボード", "損益分岐点", "資金繰り"])

with kpi_tab:
    st.subheader("主要KPI")
    top_cols = st.columns(4)
    top_cols[0].metric("売上高", format_amount_with_unit(amounts.get("REV", Decimal("0")), unit))
    top_cols[1].metric("粗利", format_amount_with_unit(amounts.get("GROSS", Decimal("0")), unit))
    top_cols[2].metric("営業利益", format_amount_with_unit(amounts.get("OP", Decimal("0")), unit))
    top_cols[3].metric("経常利益", format_amount_with_unit(amounts.get("ORD", Decimal("0")), unit))

    ratio_cols = st.columns(3)
    ratio_cols[0].metric("粗利率", format_ratio(metrics.get("gross_margin")))
    ratio_cols[1].metric("営業利益率", format_ratio(metrics.get("op_margin")))
    ratio_cols[2].metric("経常利益率", format_ratio(metrics.get("ord_margin")))

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

    st.markdown('### PLサマリー')
    pl_rows: List[Dict[str, object]] = []
    for code, label, group in ITEMS:
        if code in {'BE_SALES', 'PC_SALES', 'PC_GROSS', 'PC_ORD', 'LDR'}:
            continue
        value = amounts.get(code, Decimal('0'))
        pl_rows.append({'カテゴリ': group, '項目': label, '金額': float(value)})
    pl_df = pd.DataFrame(pl_rows)
    st.dataframe(pl_df, use_container_width=True, hide_index=True)

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
