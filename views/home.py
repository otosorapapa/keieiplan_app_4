"""Render logic for the overview / tutorial home page."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from io import BytesIO
from typing import Dict, Iterable, Mapping, Sequence

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from calc import compute, generate_cash_flow, plan_from_models, summarize_plan_metrics
from formatting import UNIT_FACTORS, format_amount_with_unit, format_ratio
from models.finance import SalesItem
from state import ensure_session_defaults, load_finance_bundle, reset_app_state
from theme import THEME_COLORS, inject_theme
from services import auth
from ui.chrome import HeaderActions, render_app_footer, render_app_header, render_usage_guide_panel
from ui.components import MetricCard, render_callout, render_metric_cards


def _safe_decimal(value: object, default: Decimal = Decimal("0")) -> Decimal:
    if value in (None, "", "NaN"):
        return default
    try:
        return Decimal(str(value))
    except Exception:  # pragma: no cover - defensive
        return default


def _unique_channels(items: Sequence[SalesItem]) -> list[str]:
    return sorted({item.channel for item in items if getattr(item, "channel", "")})


def _filter_items(items: Sequence[SalesItem], channel: str | None) -> list[SalesItem]:
    if not channel or channel == "全店舗":
        return list(items)
    return [item for item in items if item.channel == channel]


def _monthly_sales(items: Sequence[SalesItem]) -> Dict[int, Decimal]:
    totals: Dict[int, Decimal] = {month: Decimal("0") for month in range(1, 13)}
    for item in items:
        for month, value in item.monthly.by_month().items():
            totals[month] += Decimal(value)
    return totals


def _annual_sales(items: Sequence[SalesItem]) -> Decimal:
    return sum((item.annual_total for item in items), start=Decimal("0"))


def _monthly_share(monthly_values: Mapping[int, Decimal], annual_total: Decimal) -> Dict[int, Decimal]:
    if annual_total <= 0:
        uniform = Decimal("1") / Decimal("12")
        return {month: uniform for month in range(1, 13)}
    return {month: (value / annual_total if annual_total > 0 else Decimal("0")) for month, value in monthly_values.items()}


def _breakdown_by_product(items: Sequence[SalesItem], month: int) -> Dict[str, Decimal]:
    breakdown: Dict[str, Decimal] = defaultdict(Decimal)
    for item in items:
        amount = item.monthly.by_month().get(month, Decimal("0"))
        breakdown[item.product] += amount
    return breakdown


def _breakdown_by_channel(items: Sequence[SalesItem], month: int) -> Dict[str, Decimal]:
    breakdown: Dict[str, Decimal] = defaultdict(Decimal)
    for item in items:
        amount = item.monthly.by_month().get(month, Decimal("0"))
        breakdown[item.channel] += amount
    return breakdown


def _previous_year_record(records: Iterable[Mapping[str, object]], year: int) -> Mapping[str, object] | None:
    candidate: Mapping[str, object] | None = None
    for record in records:
        try:
            record_year = int(record.get("年度"))
        except Exception:
            continue
        if record_year != year:
            continue
        category = str(record.get("区分", "")).strip()
        if category == "実績":
            return record
        candidate = record
    return candidate


def _previous_year_monthly_series(
    records: Iterable[Mapping[str, object]],
    *,
    fiscal_year: int,
    monthly_shares: Mapping[int, Decimal],
    metric_key: str,
    ratio_key: str | None = None,
    scale: Decimal = Decimal("1"),
) -> Dict[int, Decimal]:
    row = _previous_year_record(records, fiscal_year - 1)
    if row is None:
        return {}
    base_total = _safe_decimal(row.get(metric_key)) * scale
    if base_total <= 0:
        return {}
    ratio_value = Decimal("1")
    if ratio_key:
        ratio_value = _safe_decimal(row.get(ratio_key), default=Decimal("0"))
        if ratio_value <= 0:
            return {}
    series: Dict[int, Decimal] = {}
    for month, share in monthly_shares.items():
        month_share = share if share > 0 else Decimal("1") / Decimal("12")
        series[month] = base_total * ratio_value * month_share
    return series


def _percent_change(current: Decimal, previous: Decimal | None) -> Decimal | None:
    if previous is None or previous == 0:
        return None
    return (current - previous) / previous


def _trend_badge(change: Decimal | None, *, label: str) -> tuple[str, str | None]:
    if change is None:
        return (f"{label}: —", None)
    percent = float(change * Decimal("100"))
    if percent > 0:
        return (f"{label}: ▲ {percent:+.1f}%", "positive")
    if percent < 0:
        return (f"{label}: ▼ {percent:+.1f}%", "negative")
    return (f"{label}: → {percent:+.1f}%", "neutral")


def _cash_flow_dataframe(monthly_flows: Sequence[Mapping[str, object]]) -> pd.DataFrame:
    df = pd.DataFrame(list(monthly_flows))
    if df.empty:
        return df
    df = df.head(12).copy()
    for column in ["operating", "investing", "financing", "interest", "principal", "net", "cumulative"]:
        if column in df.columns:
            df[column] = df[column].apply(lambda v: float(_safe_decimal(v)))
    for column in ["month_index", "year", "month"]:
        if column in df.columns:
            df[column] = df[column].apply(lambda v: int(_safe_decimal(v)))
    return df


def _build_sales_tables(
    items: Sequence[SalesItem],
    *,
    selected_month: int,
    unit: str,
    previous_year_monthly: Mapping[int, Decimal],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    factor = UNIT_FACTORS.get(unit, Decimal("1")) or Decimal("1")
    display_rows = []
    export_rows = []
    pdf_rows = []
    total_annual = _annual_sales(items)
    months_to_date = range(1, selected_month + 1)
    month_total = sum(
        (item.monthly.by_month().get(selected_month, Decimal("0")) for item in items),
        start=Decimal("0"),
    )

    for item in items:
        month_values = item.monthly.by_month()
        month_amount = month_values.get(selected_month, Decimal("0"))
        ytd_amount = sum((month_values.get(month, Decimal("0")) for month in months_to_date), start=Decimal("0"))
        annual_amount = item.annual_total
        structure = (annual_amount / total_annual * Decimal("100")) if total_annual > 0 else Decimal("0")

        display_rows.append(
            {
                "チャネル": item.channel,
                "商品": item.product,
                "月間売上": float((month_amount / factor) if factor != 0 else month_amount),
                "YTD売上": float((ytd_amount / factor) if factor != 0 else ytd_amount),
                "年間売上": float((annual_amount / factor) if factor != 0 else annual_amount),
                "構成比 (％)": float(structure),
            }
        )

        export_rows.append(
            {
                "チャネル": item.channel,
                "商品": item.product,
                "月間売上": float(month_amount),
                "YTD売上": float(ytd_amount),
                "年間売上": float(annual_amount),
                "構成比 (％)": float(structure),
            }
        )

        prev_amount_total = previous_year_monthly.get(selected_month)
        prev_amount = None
        if prev_amount_total is not None and month_total > 0:
            share = month_amount / month_total if month_total > 0 else Decimal("0")
            prev_amount = prev_amount_total * share
        prev_text = format_amount_with_unit(prev_amount, unit) if prev_amount is not None else "—"
        pdf_rows.append(
            {
                "チャネル": item.channel,
                "商品": item.product,
                "月間売上": f"{(month_amount / factor):,.1f} {unit}" if factor != 0 else f"{month_amount:,.0f}",
                "YTD売上": f"{(ytd_amount / factor):,.1f} {unit}" if factor != 0 else f"{ytd_amount:,.0f}",
                "年間売上": f"{(annual_amount / factor):,.1f} {unit}" if factor != 0 else f"{annual_amount:,.0f}",
                "構成比 (％)": f"{structure:.1f}%",
                "昨年同月参考": prev_text,
            }
        )

    display_df = pd.DataFrame(display_rows)
    if not display_df.empty:
        display_df = display_df.sort_values("月間売上", ascending=False)
    export_df = pd.DataFrame(export_rows)
    if not export_df.empty:
        export_df = export_df.sort_values("月間売上", ascending=False)
    pdf_df = pd.DataFrame(pdf_rows)
    if not pdf_df.empty:
        pdf_df = pdf_df.sort_values("月間売上", ascending=False)
    return display_df, export_df, pdf_df


def _build_sales_pdf(table: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    try:  # pragma: no cover - depends on runtime fonts
        pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))
    except Exception:
        pass
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 36
    pdf.setFont("HeiseiMin-W3", 14)
    pdf.drawString(36, y, "売上明細レポート")
    y -= 24
    pdf.setFont("HeiseiMin-W3", 10)
    if not table.empty:
        header = " | ".join(table.columns)
        pdf.drawString(36, y, header)
        y -= 16
        for _, row in table.iterrows():
            line = " | ".join(str(row[col]) for col in table.columns)
            if y < 40:
                pdf.showPage()
                pdf.setFont("HeiseiMin-W3", 10)
                y = height - 36
            pdf.drawString(36, y, line)
            y -= 14
    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


def _inventory_projection(
    monthly_cogs: Mapping[int, Decimal],
    *,
    inventory_days: Decimal,
) -> pd.DataFrame:
    records = []
    for month in range(1, 13):
        cogs = monthly_cogs.get(month, Decimal("0"))
        daily_cogs = cogs / Decimal("30") if cogs != 0 else Decimal("0")
        inventory = daily_cogs * inventory_days if inventory_days > 0 else Decimal("0")
        turnover = (cogs / inventory) if inventory > 0 else Decimal("0")
        records.append(
            {
                "月": month,
                "在庫推定": inventory,
                "売上原価": cogs,
                "月次回転率": turnover,
            }
        )
    return pd.DataFrame(records)



def render_home_page() -> None:
    """Render the redesigned management dashboard landing page."""

    inject_theme()
    ensure_session_defaults()

    header_actions: HeaderActions = render_app_header(
        title="経営計画スタジオ",
        subtitle="主要指標の15秒把握と誤操作率50%削減をめざしたトップダッシュボード。",
    )

    if header_actions.reset_requested:
        reset_app_state()
        st.experimental_rerun()

    if header_actions.logout_requested:
        st.experimental_rerun()

    if header_actions.toggled_help:
        st.session_state["show_usage_guide"] = not st.session_state.get("show_usage_guide", False)

    render_usage_guide_panel()

    settings_state: Dict[str, object] = st.session_state.get("finance_settings", {})
    unit = str(settings_state.get("unit", "百万円"))
    fte = Decimal(str(settings_state.get("fte", 20)))
    fiscal_year = int(settings_state.get("fiscal_year", 2025))
    working_capital = st.session_state.get("working_capital_profile", {})

    bundle, has_custom_inputs = load_finance_bundle()

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
    cash_summary = generate_cash_flow(amounts, bundle.capex, bundle.loans, bundle.tax)
    cash_records = (
        cash_summary.get("investment_metrics", {}).get("monthly_cash_flows", [])
        if isinstance(cash_summary, Mapping)
        else []
    )
    cash_df = _cash_flow_dataframe(cash_records)

    sales_items = bundle.sales.items
    channel_options = _unique_channels(sales_items)
    store_options = ["全店舗", *channel_options] if channel_options else ["全店舗"]

    monthly_totals_all = _monthly_sales(sales_items)
    default_month = next(
        (month for month in range(12, 0, -1) if monthly_totals_all.get(month, Decimal("0")) > 0),
        1,
    )
    month_options = list(range(1, 13))

    selected_month_state = st.session_state.get("home_selected_month", default_month)
    if selected_month_state not in month_options:
        selected_month_state = default_month
    selected_store_state = st.session_state.get("home_selected_store", store_options[0])

    filter_cols = st.columns([6, 2, 2])
    with filter_cols[1]:
        selected_month = st.selectbox(
            "期間",
            month_options,
            index=month_options.index(selected_month_state),
            format_func=lambda m: f"{m}月",
            key="home_selected_month",
        )
    with filter_cols[2]:
        store_index = store_options.index(selected_store_state) if selected_store_state in store_options else 0
        selected_store = st.selectbox(
            "店舗",
            store_options,
            index=store_index,
            key="home_selected_store",
        )

    selected_month = int(selected_month)
    selected_store = str(selected_store)

    filtered_items = _filter_items(sales_items, selected_store)
    filtered_monthly_sales = _monthly_sales(filtered_items)
    filtered_annual_sales = _annual_sales(filtered_items)
    monthly_shares = _monthly_share(filtered_monthly_sales, filtered_annual_sales)

    total_sales = Decimal(amounts.get("REV", Decimal("0")))
    filter_ratio = Decimal("0")
    if total_sales > 0 and filtered_annual_sales > 0:
        filter_ratio = min(Decimal("1"), max(Decimal("0"), filtered_annual_sales / total_sales))
    elif total_sales <= 0 and filtered_annual_sales > 0:
        filter_ratio = Decimal("1")

    gross_total = Decimal(amounts.get("GROSS", Decimal("0"))) * (filter_ratio if total_sales > 0 else Decimal("1"))
    cogs_total = Decimal(amounts.get("COGS_TTL", Decimal("0"))) * (filter_ratio if total_sales > 0 else Decimal("1"))
    opex_total = Decimal(amounts.get("OPEX_TTL", Decimal("0"))) * (filter_ratio if total_sales > 0 else Decimal("1"))
    non_op_expenses = (
        Decimal(amounts.get("NOE_INT", Decimal("0"))) + Decimal(amounts.get("NOE_OTH", Decimal("0")))
    ) * (filter_ratio if total_sales > 0 else Decimal("1"))
    non_op_income = (
        Decimal(amounts.get("NOI_MISC", Decimal("0")))
        + Decimal(amounts.get("NOI_GRANT", Decimal("0")))
        + Decimal(amounts.get("NOI_OTH", Decimal("0")))
    ) * (filter_ratio if total_sales > 0 else Decimal("1"))

    financial_state = st.session_state.get("financial_timeseries", {})
    records = financial_state.get("records") if isinstance(financial_state, Mapping) else None
    records = records if isinstance(records, list) else []

    prev_year_sales_series = _previous_year_monthly_series(
        records,
        fiscal_year=fiscal_year,
        monthly_shares=monthly_shares,
        metric_key="売上高",
        scale=filter_ratio if filter_ratio > 0 else Decimal("1"),
    )
    prev_year_gross_series = _previous_year_monthly_series(
        records,
        fiscal_year=fiscal_year,
        monthly_shares=monthly_shares,
        metric_key="売上高",
        ratio_key="粗利益率",
        scale=filter_ratio if filter_ratio > 0 else Decimal("1"),
    )

    current_month_sales = filtered_monthly_sales.get(selected_month, Decimal("0"))
    previous_year_sales = prev_year_sales_series.get(selected_month)
    sales_change = _percent_change(current_month_sales, previous_year_sales)
    sales_trend_text, sales_tone = _trend_badge(sales_change, label="前期比")

    monthly_share = monthly_shares.get(selected_month, Decimal("0"))
    monthly_gross_value = gross_total * monthly_share if gross_total > 0 else Decimal("0")
    previous_year_gross = prev_year_gross_series.get(selected_month)
    gross_change = _percent_change(monthly_gross_value, previous_year_gross)
    gross_trend_text, gross_tone = _trend_badge(gross_change, label="前期比")

    cash_scale = filter_ratio if filter_ratio > 0 else Decimal("1")
    current_cash = Decimal("0")
    previous_cash = None
    if 1 <= selected_month <= len(cash_records):
        current_cash = _safe_decimal(cash_records[selected_month - 1].get("cumulative")) * cash_scale
    if selected_month > 1 and len(cash_records) >= selected_month - 1:
        previous_cash = _safe_decimal(cash_records[selected_month - 2].get("cumulative")) * cash_scale
    cash_change = _percent_change(current_cash, previous_cash)
    cash_trend_text, cash_tone = _trend_badge(cash_change, label="前月比")

    metric_cards = [
        MetricCard(
            icon="¥",
            label="月間売上",
            value=format_amount_with_unit(current_month_sales, unit),
            description="選択した期間・店舗の売上。KGIの主要指標として常時表示します。",
            trend=sales_trend_text,
            tone=sales_tone,
            aria_label="月間売上高",
            assistive_text="月間売上のカードです。フィルタを切り替えると対象期間が更新されます。",
        ),
        MetricCard(
            icon="📈",
            label="粗利額",
            value=format_amount_with_unit(monthly_gross_value, unit),
            description="粗利＝売上 − 売上原価。利益体質の変化を追跡します。",
            trend=gross_trend_text,
            tone=gross_tone,
            aria_label="月間粗利額",
            assistive_text="粗利額のカードです。売上構成に応じて粗利を推定しています。",
        ),
        MetricCard(
            icon="💰",
            label="資金残高",
            value=format_amount_with_unit(current_cash, unit),
            description="営業・投資・財務CFの累積に基づく資金残高の推移。",
            trend=cash_trend_text,
            tone=cash_tone,
            aria_label="資金残高",
            assistive_text="資金残高のカードです。前月比で増減を矢印表示します。",
        ),
    ]
    render_metric_cards(metric_cards, grid_aria_label="KGIダッシュボード")

    st.caption(
        f"FY{fiscal_year} 計画 ｜ 表示単位: {unit} ｜ FTE: {fte} ｜ 選択: {selected_month}月 / {selected_store}"
    )

    if not has_custom_inputs:
        st.info("サンプルデータを表示しています。入力ページで保存すると、自社データに更新されます。")

    tabs = st.tabs(["売上", "粗利", "在庫", "資金"])

    factor = UNIT_FACTORS.get(unit, Decimal("1")) or Decimal("1")

    def _to_unit(value: Decimal | None) -> float:
        if value is None:
            return 0.0
        return float((value / factor) if factor != 0 else value)

    month_options_local = list(range(1, 13))
    month_labels = {month: f"M{month:02d}" for month in month_options_local}

    with tabs[0]:
        col_trend, col_product = st.columns((3, 2))

        trend_records: list[dict[str, object]] = []
        for month in month_options_local:
            month_label = month_labels[month]
            trend_records.append(
                {
                    "月": month_label,
                    "系列": "計画",
                    "金額": _to_unit(filtered_monthly_sales.get(month, Decimal("0"))),
                }
            )
            prev_value = prev_year_sales_series.get(month)
            if prev_value is not None:
                trend_records.append({"月": month_label, "系列": "昨年", "金額": _to_unit(prev_value)})
        trend_df = pd.DataFrame(trend_records)
        if trend_df.empty:
            col_trend.info("売上データが不足しています。入力ページで売上計画を登録してください。")
        else:
            trend_fig = px.line(trend_df, x="月", y="金額", color="系列", markers=True)
            trend_fig.update_layout(
                title="売上トレンド（12か月）",
                yaxis_title=f"金額 ({unit})",
                legend_title="区分",
                margin=dict(t=40, r=16, l=24, b=16),
            )
            col_trend.plotly_chart(trend_fig, use_container_width=True)

        product_breakdown = _breakdown_by_product(filtered_items, selected_month)
        product_records = sorted(product_breakdown.items(), key=lambda pair: pair[1], reverse=True)[:5]
        if not product_records:
            col_product.info("選択した条件で商品別売上は登録されていません。")
        else:
            product_df = pd.DataFrame(
                [{"商品": name, "売上": _to_unit(value)} for name, value in product_records]
            )
            product_fig = px.bar(
                product_df,
                x="売上",
                y="商品",
                orientation="h",
                text=product_df["売上"].map(lambda v: f"{v:,.1f}"),
            )
            product_fig.update_layout(
                title="商品別売上（上位5件）",
                xaxis_title=f"金額 ({unit})",
                yaxis_title="商品",
                margin=dict(t=40, r=16, l=120, b=16),
            )
            product_fig.update_traces(textposition="outside")
            col_product.plotly_chart(product_fig, use_container_width=True)

        channel_breakdown = _breakdown_by_channel(filtered_items, selected_month)
        channel_records = sorted(channel_breakdown.items(), key=lambda pair: pair[1], reverse=True)
        if channel_records:
            channel_df = pd.DataFrame(
                [{"チャネル": name, "売上": _to_unit(value)} for name, value in channel_records]
            )
            channel_fig = px.bar(channel_df, x="チャネル", y="売上", text="売上")
            channel_fig.update_layout(
                title="チャネル別売上構成",
                yaxis_title=f"金額 ({unit})",
                margin=dict(t=40, r=16, l=24, b=16),
            )
            channel_fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
            st.plotly_chart(channel_fig, use_container_width=True)
        else:
            st.info("チャネル別の内訳は表示できません。チャネルを追加してください。")

        display_df, export_df, pdf_df = _build_sales_tables(
            filtered_items,
            selected_month=selected_month,
            unit=unit,
            previous_year_monthly=prev_year_sales_series,
        )
        if display_df.empty:
            st.info("売上明細テーブルを表示するには、売上計画を登録してください。")
        else:
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "月間売上": st.column_config.NumberColumn("月間売上", format=f"%.1f {unit}"),
                    "YTD売上": st.column_config.NumberColumn("YTD売上", format=f"%.1f {unit}"),
                    "年間売上": st.column_config.NumberColumn("年間売上", format=f"%.1f {unit}"),
                    "構成比 (％)": st.column_config.NumberColumn("構成比 (％)", format="%.1f"),
                },
            )

        csv_bytes = export_df.to_csv(index=False).encode("utf-8-sig")
        pdf_bytes = _build_sales_pdf(pdf_df)
        download_cols = st.columns(2)
        download_cols[0].download_button(
            "CSVダウンロード",
            data=csv_bytes,
            file_name=f"sales_detail_FY{fiscal_year}_M{selected_month:02d}.csv",
            mime="text/csv",
            disabled=export_df.empty,
        )
        download_cols[1].download_button(
            "PDFダウンロード",
            data=pdf_bytes,
            file_name=f"sales_detail_FY{fiscal_year}_M{selected_month:02d}.pdf",
            mime="application/pdf",
            disabled=pdf_df.empty,
        )

    with tabs[1]:
        st.metric("年間粗利率", format_ratio(metrics.get("gross_margin")))

        margin_records: list[dict[str, object]] = []
        for month in month_options_local:
            month_label = month_labels[month]
            sales_value = filtered_monthly_sales.get(month, Decimal("0"))
            gross_value = gross_total * monthly_shares.get(month, Decimal("0")) if gross_total > 0 else Decimal("0")
            ratio = gross_value / sales_value if sales_value > 0 else Decimal("0")
            margin_records.append({"月": month_label, "系列": "計画", "粗利率": float(ratio * Decimal("100"))})
            prev_sales = prev_year_sales_series.get(month)
            prev_gross = prev_year_gross_series.get(month)
            if prev_sales and prev_sales > 0 and prev_gross is not None:
                prev_ratio = prev_gross / prev_sales
                margin_records.append({"月": month_label, "系列": "昨年", "粗利率": float(prev_ratio * Decimal("100"))})
        margin_df = pd.DataFrame(margin_records)
        if margin_df.empty:
            st.info("粗利率グラフを描画するには、売上と原価のデータが必要です。")
        else:
            margin_fig = px.line(margin_df, x="月", y="粗利率", color="系列", markers=True)
            margin_fig.update_layout(
                title="粗利率推移",
                yaxis_title="粗利率 (％)",
                margin=dict(t=40, r=16, l=24, b=16),
            )
            st.plotly_chart(margin_fig, use_container_width=True)

        cost_breakdown = {
            "売上原価": _to_unit(cogs_total),
            "固定費": _to_unit(opex_total),
            "営業外費用": _to_unit(non_op_expenses),
        }
        if non_op_income > 0:
            cost_breakdown["営業外収益"] = _to_unit(non_op_income)
        total_cost = sum(cost_breakdown.values())
        if total_cost <= 0:
            st.info("原価構成グラフを表示するには、費用データが必要です。")
        else:
            category_label = "費用構成"
            axis_position = 0.0
            cost_records = [
                {"表示": "内訳", "軸": axis_position, "項目": name, "金額": value}
                for name, value in cost_breakdown.items()
            ]
            cost_records.append(
                {"表示": "合計", "軸": axis_position, "項目": "合計固定費", "金額": total_cost}
            )
            cost_df = pd.DataFrame(cost_records)
            segment_df = cost_df[cost_df["表示"] == "内訳"].copy()

            color_keys = ["primary", "accent", "positive", "warning", "chart_purple", "chart_green"]
            color_sequence = [THEME_COLORS.get(key, THEME_COLORS["accent"]) for key in color_keys]

            cost_fig = px.bar(
                segment_df,
                x="金額",
                y="軸",
                color="項目",
                orientation="h",
                barmode="stack",
                color_discrete_sequence=color_sequence,
                custom_data=["項目"],
            )
            cost_fig.update_traces(
                hovertemplate="%{customdata[0]}: %{x:,.1f} " + unit + "<extra></extra>"
            )
            cost_fig.update_yaxes(
                tickmode="array",
                tickvals=[axis_position],
                ticktext=[category_label],
                title="",
                showgrid=False,
                zeroline=False,
                range=[axis_position - 0.6, axis_position + 0.6],
            )
            cost_fig.update_xaxes(title=f"金額 ({unit})")
            cost_fig.update_layout(
                title="原価・費用構成",
                margin=dict(t=40, r=16, l=16, b=16),
                legend_title="項目",
            )

            cost_fig.add_trace(
                go.Scatter(
                    x=[total_cost, total_cost],
                    y=[axis_position - 0.45, axis_position + 0.45],
                    mode="lines",
                    name="合計固定費",
                    line=dict(color=THEME_COLORS["primary_light"], width=2, dash="dash"),
                    hovertemplate="合計固定費: %{x:,.1f} " + unit + "<extra></extra>",
                    showlegend=True,
                )
            )

            st.plotly_chart(cost_fig, use_container_width=True)
            st.caption("積み上げ棒グラフは費用の内訳を示し、破線が合計固定費の計画値を表します。")

        gross_ratio_total = gross_total / filtered_annual_sales if filtered_annual_sales > 0 else Decimal("0")
        month_total_sales = sum(
            (item.monthly.by_month().get(selected_month, Decimal("0")) for item in filtered_items),
            start=Decimal("0"),
        )
        gross_rows: list[dict[str, object]] = []
        for item in filtered_items:
            month_values = item.monthly.by_month()
            month_amount = month_values.get(selected_month, Decimal("0"))
            ytd_amount = sum(
                (month_values.get(month, Decimal("0")) for month in range(1, selected_month + 1)),
                start=Decimal("0"),
            )
            annual_amount = item.annual_total
            month_gross = month_amount * gross_ratio_total
            ytd_gross = ytd_amount * gross_ratio_total
            annual_gross = annual_amount * gross_ratio_total
            prev_total = prev_year_gross_series.get(selected_month)
            prev_item = None
            if prev_total is not None and month_total_sales > 0:
                prev_item = prev_total * (month_amount / month_total_sales)
            gross_rows.append(
                {
                    "チャネル": item.channel,
                    "商品": item.product,
                    "月間粗利": float((month_gross / factor) if factor != 0 else month_gross),
                    "YTD粗利": float((ytd_gross / factor) if factor != 0 else ytd_gross),
                    "年間粗利": float((annual_gross / factor) if factor != 0 else annual_gross),
                    "昨年同月推定": float((prev_item / factor) if (prev_item is not None and factor != 0) else (prev_item or Decimal("0"))),
                }
            )
        gross_table = pd.DataFrame(gross_rows)
        if gross_table.empty:
            st.info("粗利テーブルを表示するには、売上と原価のデータが必要です。")
        else:
            st.dataframe(
                gross_table,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "月間粗利": st.column_config.NumberColumn("月間粗利", format=f"%.1f {unit}"),
                    "YTD粗利": st.column_config.NumberColumn("YTD粗利", format=f"%.1f {unit}"),
                    "年間粗利": st.column_config.NumberColumn("年間粗利", format=f"%.1f {unit}"),
                    "昨年同月推定": st.column_config.NumberColumn("昨年同月推定", format=f"%.1f {unit}"),
                },
            )

    with tabs[2]:
        inventory_days = Decimal(str(working_capital.get("inventory_days", 30)))
        monthly_cogs = {month: cogs_total * monthly_shares.get(month, Decimal("0")) for month in month_options_local}
        inventory_projection = _inventory_projection(monthly_cogs, inventory_days=inventory_days)
        inventory_values = [value for value in inventory_projection["在庫推定"]]
        avg_inventory = (
            sum(inventory_values, start=Decimal("0")) / Decimal(len(inventory_values))
            if inventory_values
            else Decimal("0")
        )
        turnover = (cogs_total / avg_inventory) if avg_inventory > 0 else Decimal("0")

        st.metric(
            "推定在庫回転率",
            f"{turnover:.1f}回" if turnover > 0 else "—",
            delta=f"在庫日数 {inventory_days}日",
        )

        inventory_chart_df = inventory_projection.copy()
        inventory_chart_df["月"] = inventory_chart_df["月"].map(lambda m: month_labels[int(m)])
        inventory_chart_df["在庫推定"] = inventory_chart_df["在庫推定"].map(_to_unit)
        if inventory_chart_df["在庫推定"].sum() <= 0:
            st.info("在庫推移を表示するには、売上原価と在庫日数を設定してください。")
        else:
            inventory_fig = px.line(inventory_chart_df, x="月", y="在庫推定", markers=True)
            inventory_fig.update_layout(
                title="在庫推移（推定）",
                yaxis_title=f"在庫水準 ({unit})",
                margin=dict(t=40, r=16, l=24, b=16),
            )
            st.plotly_chart(inventory_fig, use_container_width=True)

        inventory_table = inventory_projection.copy()
        inventory_table["月"] = inventory_table["月"].map(lambda m: month_labels[int(m)])
        inventory_table["在庫推定"] = inventory_table["在庫推定"].map(_to_unit)
        inventory_table["売上原価"] = inventory_table["売上原価"].map(_to_unit)
        inventory_table["月次回転率"] = inventory_table["月次回転率"].map(lambda v: float(v))
        st.dataframe(
            inventory_table,
            use_container_width=True,
            hide_index=True,
            column_config={
                "在庫推定": st.column_config.NumberColumn("在庫推定", format=f"%.1f {unit}"),
                "売上原価": st.column_config.NumberColumn("売上原価", format=f"%.1f {unit}"),
                "月次回転率": st.column_config.NumberColumn("月次回転率", format="%.2f"),
            },
        )

    with tabs[3]:
        cash_display = cash_df.copy()
        if cash_display.empty:
            st.info("キャッシュフローデータが不足しています。投資・借入の設定を確認してください。")
        else:
            cash_display["月"] = cash_display["month"].apply(lambda m: month_labels.get(int(m), f"M{int(m):02d}"))
            if "year" in cash_display.columns:
                cash_display["年度"] = cash_display["year"].astype(int)
            divisor = float(factor) if factor != 0 else 1.0
            for column in ["operating", "investing", "financing", "net", "cumulative"]:
                if column in cash_display.columns:
                    cash_display[column] = cash_display[column] / divisor

            cash_line = px.line(cash_display, x="月", y="cumulative", markers=True)
            cash_line.update_layout(
                title="資金残高推移",
                yaxis_title=f"残高 ({unit})",
                margin=dict(t=40, r=16, l=24, b=16),
            )
            st.plotly_chart(cash_line, use_container_width=True)

            cash_fig = go.Figure()
            for column, label in [
                ("operating", "営業CF"),
                ("investing", "投資CF"),
                ("financing", "財務CF"),
            ]:
                if column in cash_display.columns:
                    cash_fig.add_trace(go.Bar(x=cash_display["月"], y=cash_display[column], name=label))
            cash_fig.update_layout(
                title="キャッシュフロー構成",
                yaxis_title=f"金額 ({unit})",
                barmode="relative",
                margin=dict(t=40, r=16, l=24, b=16),
            )
            st.plotly_chart(cash_fig, use_container_width=True)

            display_columns = [
                col
                for col in ["年度", "月", "operating", "investing", "financing", "net", "cumulative"]
                if col in cash_display.columns
            ]
            st.dataframe(
                cash_display[display_columns],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "operating": st.column_config.NumberColumn("営業CF", format=f"%.1f {unit}"),
                    "investing": st.column_config.NumberColumn("投資CF", format=f"%.1f {unit}"),
                    "financing": st.column_config.NumberColumn("財務CF", format=f"%.1f {unit}"),
                    "net": st.column_config.NumberColumn("純増減", format=f"%.1f {unit}"),
                    "cumulative": st.column_config.NumberColumn("累積残高", format=f"%.1f {unit}"),
                },
            )

    if not auth.is_authenticated():
        render_callout(
            icon="🔐",
            title="ログインでクラウド保存とバージョン管理を解放",
            body="ヘッダー右上の「ログイン」からアカウントを作成すると、暗号化ストレージへの保存と履歴管理が利用できます。",
            tone="caution",
            aria_label="ログイン案内",
        )

    render_app_footer(
        caption="© 経営計画スタジオ | ダッシュボードで意思決定を高速化します。",
    )
