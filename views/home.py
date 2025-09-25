"""Streamlit home view for the phase-2 dashboard IA prototype."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO
from typing import Iterable

import pandas as pd
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas


DESIGN_TOKENS: dict[str, str] = {
    "primary": "#0B1F3B",
    "secondary": "#5A6B7A",
    "accent": "#1E88E5",
    "background": "#F7F8FA",
    "card_bg": "#FFFFFF",
    "success": "#56A559",
    "warning": "#E69319",
    "error": "#E15349",
}


# --- Session defaults & constants ----------------------------------------------------

SESSION_KEYS: dict[str, str] = {
    "period": "今月",
    "store": "本店",
    "grain": "日次",
}

TAB_LABELS: list[str] = ["売上", "粗利", "在庫", "資金"]
PERIOD_OPTIONS = ["本日", "今週", "今月", "前年同月"]
STORE_OPTIONS = ["本店", "A店", "EC"]
GRAIN_OPTIONS = ["日次", "週次", "月次"]
EVENT_LOG_KEY = "_dashboard_events"


@dataclass
class DashboardContext:
    """Simple container for shared filter state."""

    period: str
    store: str
    grain: str


@dataclass
class TabArtifacts:
    """Artifacts generated while rendering a tab (for reuse elsewhere)."""

    detail_rows: int
    csv_bytes: bytes


# --- Helpers ------------------------------------------------------------------------

def _ensure_session_defaults() -> None:
    """Ensure the dashboard specific keys exist in session state."""

    for key, value in SESSION_KEYS.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if EVENT_LOG_KEY not in st.session_state:
        st.session_state[EVENT_LOG_KEY] = []


def _log_event(name: str, **params: object) -> None:
    """Append an analytics style event to the session log."""

    st.session_state[EVENT_LOG_KEY].append(
        {
            "event": name,
            "params": params,
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
        }
    )


def _inject_responsive_styles() -> None:
    """Inject CSS for the <768px responsive breakpoints and helper styles."""

    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Source+Sans+3:wght@400;600&display=swap');
        :root {
            --kp-primary: %(primary)s;
            --kp-secondary: %(secondary)s;
            --kp-accent: %(accent)s;
            --kp-background: %(background)s;
            --kp-card-bg: %(card_bg)s;
            --kp-success: %(success)s;
            --kp-warning: %(warning)s;
            --kp-error: %(error)s;
        }
        html, body, [class*="stApp"]  {
            font-family: "Inter", "Source Sans 3", "Noto Sans JP", sans-serif;
            color: #1A1A1A;
            font-variant-numeric: tabular-nums;
        }
        .dashboard-kpi-row, .dashboard-filter-row {
            gap: 1.5rem;
        }
        .dashboard-kpi-row > div[data-testid="column"],
        .dashboard-filter-row > div[data-testid="column"] {
            min-width: 0 !important;
        }
        .dashboard-kpi-row div[data-testid="metric-container"] {
            background-color: var(--kp-card-bg);
            border-radius: 12px;
            padding: 1.25rem 1.5rem;
            box-shadow: 0 4px 12px rgba(11, 31, 59, 0.08);
            border: 1px solid rgba(11, 31, 59, 0.08);
        }
        div[data-testid="metric-container"] label[data-testid="stMetricLabel"] {
            color: var(--kp-secondary);
            font-weight: 600;
        }
        div[data-testid="metric-container"] [data-testid="stMetricValue"] {
            color: var(--kp-primary);
            font-size: 2rem;
        }
        div[data-testid="metric-container"] [data-testid="stMetricDelta"] {
            font-size: 0.95rem;
        }
        .dashboard-tabs .stTabs [data-baseweb="tab"] {
            background-color: transparent;
            border-bottom: 2px solid transparent;
            padding: 0.75rem 1rem;
            font-weight: 600;
            color: var(--kp-secondary);
        }
        .dashboard-tabs .stTabs [aria-selected="true"] {
            border-bottom-color: var(--kp-primary);
            color: var(--kp-primary);
        }
        .dashboard-tabs .stTabs [data-baseweb="tab-list"] {
            gap: 0.5rem;
        }
        .dashboard-card {
            background-color: var(--kp-card-bg);
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: 0 6px 16px rgba(11, 31, 59, 0.08);
            border: 1px solid rgba(11, 31, 59, 0.08);
        }
        @media (max-width: 768px) {
            .dashboard-kpi-row > div[data-testid="column"],
            .dashboard-filter-row > div[data-testid="column"] {
                flex: 0 0 100% !important;
                width: 100% !important;
            }
            .dashboard-tabs .stTabs {
                overflow-x: auto;
            }
        }
        </style>
        """
        % DESIGN_TOKENS,
        unsafe_allow_html=True,
    )


def _render_filters() -> DashboardContext:
    """Render the period/store/grain selectors and update session state."""

    previous_values = {
        "period": st.session_state["period"],
        "store": st.session_state["store"],
        "grain": st.session_state["grain"],
    }

    st.markdown('<div class="dashboard-filter-row">', unsafe_allow_html=True)
    f1, f2, f3 = st.columns(3)
    with f1:
        period = st.selectbox(
            "期間",
            PERIOD_OPTIONS,
            index=PERIOD_OPTIONS.index(previous_values["period"]),
        )
    with f2:
        store = st.selectbox(
            "店舗",
            STORE_OPTIONS,
            index=STORE_OPTIONS.index(previous_values["store"]),
        )
    with f3:
        grain = st.selectbox(
            "粒度",
            GRAIN_OPTIONS,
            index=GRAIN_OPTIONS.index(previous_values["grain"]),
        )
    st.markdown("</div>", unsafe_allow_html=True)

    if period != previous_values["period"]:
        st.session_state["period"] = period
        _log_event("select_period", 新値=period)
    if store != previous_values["store"]:
        st.session_state["store"] = store
        _log_event("select_store", 新値=store)
    if grain != previous_values["grain"]:
        st.session_state["grain"] = grain
        _log_event("select_grain", 新値=grain)

    return DashboardContext(period=period, store=store, grain=grain)


def _render_home_summary(ctx: DashboardContext) -> None:
    """Render top KPI cards based on the design tokens."""

    st.markdown('<div class="dashboard-kpi-row">', unsafe_allow_html=True)
    k1, k2, k3 = st.columns(3)
    with k1:
        st.metric("売上対予実差[%]", "+4.2pt", "+0.8pt", delta_color="normal")
    with k2:
        st.metric("粗利率[%]", "32.1%", "-0.8pt", delta_color="inverse")
    with k3:
        st.metric("資金残高[千円]", "12,300千円", "+320千円", delta_color="normal")
    st.markdown("</div>", unsafe_allow_html=True)
    st.caption(f"{ctx.period} / {ctx.store} / {ctx.grain} で集計")
    st.markdown(
        "<div class='dashboard-card' style='margin-top:1rem;'>"
        "<strong style='color:var(--kp-secondary);'>警戒アラート</strong><br/>"
        "粗利率30%未満のSKUは12件。重点フォローを推奨します。"
        "</div>",
        unsafe_allow_html=True,
    )
    _log_event("view_alert", alert_type="gross_margin", count=12)


def _synthetic_dates(days: int) -> Iterable[str]:
    today = datetime.today()
    return [(today - timedelta(days=days - idx - 1)).strftime("%m/%d") for idx in range(days)]


def _render_trend_chart(title: str, data: pd.DataFrame, *, use_budget: bool = False) -> None:
    st.subheader(title)
    chart_df = data.set_index("index")
    if use_budget:
        actual_cols = [col for col in chart_df.columns if "実績" in col]
        budget_cols = [col for col in chart_df.columns if "予算" in col]
        selected = actual_cols + budget_cols
        if selected:
            st.line_chart(chart_df[selected], height=260)
            return
    st.line_chart(chart_df, height=260)


def _render_breakdown_bars(title: str, data: pd.DataFrame) -> None:
    st.subheader(title)
    st.bar_chart(data.set_index("項目"), height=260)


def _render_table(title: str, data: pd.DataFrame, *, highlights: bool = False) -> None:
    st.subheader(title)
    if data.empty:
        st.info("該当データがありません。期間/店舗を変えて再実行してください。")
        st.button("再実行")
        return

    column_config: dict[str, st.column_config.Column] = {}
    for column in data.columns:
        if column.endswith('[%]'):
            column_config[column] = st.column_config.NumberColumn(column, format='%.1f%%')
        elif column.endswith('[千円]'):
            column_config[column] = st.column_config.NumberColumn(column, format='%,.0f')
        elif column.endswith('[円]'):
            column_config[column] = st.column_config.NumberColumn(column, format='%,.0f円')
        elif column.endswith('[日]') or column.endswith('[件]'):
            column_config[column] = st.column_config.NumberColumn(column, format='%,.0f')
        elif column in {"数量", "在庫数", "販売予測"}:
            column_config[column] = st.column_config.NumberColumn(column, format='%,.0f')

    dataframe: pd.DataFrame | pd.io.formats.style.Styler
    if highlights:
        dataframe = data.style.apply(
            lambda row: ["background-color: #FFE8E8" if "過多" in str(value) else "" for value in row],
            axis=1,
        )
    else:
        dataframe = data

    st.dataframe(
        dataframe,
        column_config=column_config,
        hide_index=True,
        use_container_width=True,
    )


def _download_buttons(prefix: str, dataframe: pd.DataFrame, *, enable_pdf: bool = False) -> TabArtifacts:
    csv_bytes = dataframe.to_csv(index=False).encode("utf-8-sig")
    cols = st.columns(2 if enable_pdf else 1)
    with cols[0]:
        if st.download_button("CSVダウンロード", data=csv_bytes, file_name=f"{prefix}.csv"):
            _log_event("download_csv", tab_name=prefix, row_count=len(dataframe))
    if enable_pdf:
        pdf_bytes = _build_pdf_report(prefix, dataframe)
        with cols[1]:
            st.download_button("PDFダウンロード", data=pdf_bytes, file_name=f"{prefix}.pdf")
    return TabArtifacts(detail_rows=len(dataframe), csv_bytes=csv_bytes)


def _build_pdf_report(title: str, dataframe: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setFont("HeiseiKakuGo-W5", 16)
    pdf.drawString(40, 800, f"{title}レポート")
    pdf.setFont("HeiseiKakuGo-W5", 12)
    y = 770
    for column in dataframe.columns:
        pdf.drawString(40, y, column)
        y -= 14
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


# --- Tab renderers ------------------------------------------------------------------

def _render_sales_tab(ctx: DashboardContext, *, active: bool) -> TabArtifacts:
    st.caption("指標: 売上対予実差[%] / 進捗率[%] / 客単価[円]")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("売上対予実差[%]", "+8.5pt", "+1.2pt", delta_color="normal")
    with c2:
        st.metric("進捗率[%]", "74.0%", "-6.0pt", delta_color="inverse")
    with c3:
        st.metric("客単価[円]", "12,320円", "+320円", delta_color="normal")

    trend_df = pd.DataFrame(
        {
            "index": _synthetic_dates(10),
            "実績[百万円]": [112, 118, 121, 134, 128, 139, 150, 154, 160, 168],
            "予算[百万円]": [110, 115, 120, 130, 132, 136, 142, 148, 152, 158],
        }
    )
    trend_col, breakdown_col = st.columns((3, 2))
    with trend_col:
        _render_trend_chart("売上トレンド", trend_df, use_budget=True)
    with breakdown_col:
        product_df = pd.DataFrame(
            {
                "項目": ["商品A", "商品B", "商品C", "商品D", "商品E"],
                "売上[千円]": [450, 420, 380, 320, 270],
            }
        )
        _render_breakdown_bars("商品売上TOP5[千円]", product_df)

    composition_df = pd.DataFrame(
        {
            "index": _synthetic_dates(6),
            "店頭[%]": [52, 51, 50, 49, 48, 47],
            "EC[%]": [28, 29, 30, 31, 32, 33],
            "卸[%]": [12, 12, 12, 12, 12, 12],
            "海外[%]": [8, 8, 8, 8, 8, 8],
        }
    )
    st.subheader("チャネル構成比推移")
    st.area_chart(composition_df.set_index("index"), height=220)

    detail_df = pd.DataFrame(
        [
            {"日付": "10/01", "店舗": ctx.store, "商品": "商品A", "数量": 120, "売上[千円]": 540, "粗利[千円]": 168, "粗利率[%]": 31.1},
            {"日付": "10/01", "店舗": ctx.store, "商品": "商品B", "数量": 95, "売上[千円]": 430, "粗利[千円]": 142, "粗利率[%]": 33.0},
            {"日付": "10/02", "店舗": ctx.store, "商品": "商品C", "数量": 102, "売上[千円]": 408, "粗利[千円]": 128, "粗利率[%]": 31.4},
            {"日付": "10/02", "店舗": ctx.store, "商品": "商品D", "数量": 88, "売上[千円]": 352, "粗利[千円]": 102, "粗利率[%]": 29.0},
        ]
    )
    _render_table("明細", detail_df)
    artifacts = _download_buttons("sales", detail_df, enable_pdf=True)
    return artifacts


def _render_margin_tab(ctx: DashboardContext, *, active: bool) -> TabArtifacts:
    st.caption("指標: 粗利率[%] / 前月差[pt] / 粗利額[千円]")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("粗利率[%]", "31.2%", "-0.6pt", delta_color="inverse")
    with c2:
        st.metric("前月差[pt]", "-0.6pt", "-0.6pt", delta_color="inverse")
    with c3:
        st.metric("粗利額[千円]", "5,480千円", "-120千円", delta_color="inverse")

    margin_trend = pd.DataFrame(
        {
            "index": _synthetic_dates(10),
            "粗利率[%]": [33.2, 32.8, 32.4, 32.1, 31.9, 31.6, 31.4, 31.2, 31.0, 30.8],
        }
    )
    trend_col, breakdown_col = st.columns((3, 2))
    with trend_col:
        _render_trend_chart("粗利率トレンド", margin_trend)
    with breakdown_col:
        cause_df = pd.DataFrame(
            {
                "項目": ["値引", "仕入高騰", "構成変化", "在庫処分", "販促費"],
                "粗利影響[千円]": [-68, -54, -43, -32, -28],
            }
        )
        _render_breakdown_bars("粗利悪化要因TOP5[千円]", cause_df)

    mix_df = pd.DataFrame(
        {
            "index": _synthetic_dates(6),
            "主力SKU[%]": [46, 45, 44, 44, 43, 42],
            "準主力SKU[%]": [32, 32, 33, 33, 34, 34],
            "新商品[%]": [12, 13, 13, 13, 13, 13],
            "長尾SKU[%]": [10, 10, 10, 10, 10, 11],
        }
    )
    st.subheader("商品構成比推移")
    st.area_chart(mix_df.set_index("index"), height=220)

    detail_df = pd.DataFrame(
        [
            {"日付": "10/01", "商品": "商品A", "売上[千円]": 540, "粗利[千円]": 168, "粗利率[%]": 31.1, "対前月差[pt]": -0.5},
            {"日付": "10/01", "商品": "商品B", "売上[千円]": 430, "粗利[千円]": 142, "粗利率[%]": 33.0, "対前月差[pt]": -0.6},
            {"日付": "10/02", "商品": "商品C", "売上[千円]": 408, "粗利[千円]": 128, "粗利率[%]": 31.4, "対前月差[pt]": -0.7},
            {"日付": "10/02", "商品": "商品D", "売上[千円]": 352, "粗利[千円]": 102, "粗利率[%]": 29.0, "対前月差[pt]": -0.8},
        ]
    )
    _render_table("明細", detail_df)
    artifacts = _download_buttons("gross_margin", detail_df, enable_pdf=False)
    return artifacts


def _render_inventory_tab(ctx: DashboardContext, *, active: bool) -> TabArtifacts:
    st.caption("指標: 在庫金額[千円] / 回転日数[日] / 欠品率[%]")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("在庫金額[千円]", "23,400千円", "-1,200千円", delta_color="inverse")
    with c2:
        st.metric("回転日数[日]", "45日", "+5日", delta_color="inverse")
    with c3:
        st.metric("欠品率[%]", "1.2%", "-0.3pt", delta_color="inverse")

    inventory_trend = pd.DataFrame(
        {
            "index": _synthetic_dates(10),
            "在庫金額[百万円]": [26.4, 26.1, 25.8, 25.2, 24.8, 24.2, 23.9, 23.6, 23.4, 23.2],
        }
    )
    trend_col, breakdown_col = st.columns((3, 2))
    with trend_col:
        _render_trend_chart("在庫金額トレンド", inventory_trend)
    with breakdown_col:
        category_df = pd.DataFrame(
            {
                "項目": ["カテゴリA", "カテゴリB", "カテゴリC", "カテゴリD", "カテゴリE"],
                "在庫金額[千円]": [5200, 4800, 4100, 3600, 3200],
            }
        )
        _render_breakdown_bars("滞留カテゴリTOP5[千円]", category_df)

    coverage_df = pd.DataFrame(
        {
            "index": _synthetic_dates(6),
            "良品[%]": [64, 65, 65, 66, 67, 67],
            "滞留[%]": [18, 17, 17, 16, 15, 15],
            "欠品[%]": [6, 6, 6, 6, 6, 6],
            "廃棄予定[%]": [12, 12, 12, 12, 12, 12],
        }
    )
    st.subheader("在庫区分構成比推移")
    st.area_chart(coverage_df.set_index("index"), height=220)

    detail_df = pd.DataFrame(
        [
            {"SKU": "SKU-001", "在庫数": 1200, "在庫金額[千円]": 5400, "回転日数[日]": 60, "販売予測": 400, "状況": "過多"},
            {"SKU": "SKU-002", "在庫数": 900, "在庫金額[千円]": 4600, "回転日数[日]": 52, "販売予測": 350, "状況": "過多"},
            {"SKU": "SKU-003", "在庫数": 780, "在庫金額[千円]": 3800, "回転日数[日]": 48, "販売予測": 300, "状況": "注意"},
            {"SKU": "SKU-004", "在庫数": 620, "在庫金額[千円]": 3200, "回転日数[日]": 38, "販売予測": 280, "状況": "注意"},
        ]
    )
    _render_table("明細", detail_df, highlights=True)
    artifacts = _download_buttons("inventory", detail_df, enable_pdf=False)
    return artifacts


def _render_cash_tab(ctx: DashboardContext, *, active: bool) -> TabArtifacts:
    st.caption("指標: 営業CF[千円] / フリーCF[千円] / 資金残高[千円]")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("営業CF[千円]", "1,820千円", "+120千円", delta_color="normal")
    with c2:
        st.metric("フリーCF[千円]", "1,240千円", "+80千円", delta_color="normal")
    with c3:
        st.metric("月末残高[千円]", "12,300千円", "+320千円", delta_color="normal")

    cash_df = pd.DataFrame(
        {
            "index": _synthetic_dates(6),
            "入金[百万円]": [62, 64, 58, 60, 65, 68],
            "出金[百万円]": [-42, -45, -44, -43, -41, -40],
            "残高[百万円]": [20, 23, 21, 23, 24, 27],
        }
    )
    trend_col, breakdown_col = st.columns((3, 2))
    with trend_col:
        _render_trend_chart("資金繰りトレンド", cash_df)
    with breakdown_col:
        flow_df = pd.DataFrame(
            {
                "項目": ["売掛回収", "在庫圧縮", "人件費", "投資支出", "販促費"],
                "キャッシュ影響[千円]": [680, 420, -520, -380, -260],
            }
        )
        _render_breakdown_bars("資金流入出TOP5[千円]", flow_df)

    balance_mix = pd.DataFrame(
        {
            "index": _synthetic_dates(6),
            "運転資金[%]": [58, 57, 56, 55, 54, 53],
            "投資資金[%]": [18, 19, 19, 19, 19, 20],
            "余剰資金[%]": [24, 24, 25, 26, 27, 27],
        }
    )
    st.subheader("資金構成比推移")
    st.area_chart(balance_mix.set_index("index"), height=220)

    detail_df = pd.DataFrame(
        [
            {"日付": "10/01", "入金[千円]": 620, "出金[千円]": 420, "営業CF[千円]": 200, "残高[千円]": 200},
            {"日付": "10/05", "入金[千円]": 640, "出金[千円]": 450, "営業CF[千円]": 190, "残高[千円]": 230},
            {"日付": "10/10", "入金[千円]": 580, "出金[千円]": 440, "営業CF[千円]": 140, "残高[千円]": 210},
            {"日付": "10/15", "入金[千円]": 600, "出金[千円]": 430, "営業CF[千円]": 170, "残高[千円]": 230},
        ]
    )
    _render_table("明細", detail_df)
    artifacts = _download_buttons("cash", detail_df, enable_pdf=False)
    return artifacts


TAB_RENDERERS = {
    "売上": _render_sales_tab,
    "粗利": _render_margin_tab,
    "在庫": _render_inventory_tab,
    "資金": _render_cash_tab,
}


# --- Public entrypoint --------------------------------------------------------------

def render_home_page() -> None:
    """Render the redesigned dashboard home following the IA specification."""

    _ensure_session_defaults()
    _inject_responsive_styles()

    st.title("経営ダッシュボード")
    st.caption("KGI直結の指標を一目で把握し、3クリック以内で深掘りできるホーム画面")

    summary_placeholder = st.container()

    with st.container():
        tab_col, filter_col = st.columns((3, 2))
        with filter_col:
            ctx = _render_filters()
        with tab_col:
            tabs = st.tabs(TAB_LABELS)

    with summary_placeholder:
        _render_home_summary(ctx)

    _log_event("view_home", period=ctx.period, store=ctx.store)

    tab_artifacts: dict[str, TabArtifacts] = {}
    for label, tab in zip(TAB_LABELS, tabs):
        with tab:
            tab_artifacts[label] = TAB_RENDERERS[label](ctx, active=True)

    counts_summary = " / ".join(f"{label}: {artifact.detail_rows}件" for label, artifact in tab_artifacts.items())
    st.caption(f"明細件数サマリー: {counts_summary}")

    with st.expander(":grey_question: 用語集", expanded=False):
        st.markdown(
            """
            - **売上対予実差**: (実績−予算)/予算。
            - **粗利率**: 粗利÷売上。対前月をデフォルト比較。
            - **在庫回転日数**: 在庫÷日次売上。値が大きいほど悪化。
            - **営業CF**: 営業活動によるキャッシュフロー。
            """
        )

    st.caption("取得に失敗した場合は接続/権限をご確認のうえ再試行してください。")

    st.markdown(
        "<div class='dashboard-card' style='margin-top:1.5rem;'>"
        "<strong style='color:var(--kp-primary);'>効果見込み（Fermi）</strong><ul style='padding-left:1.2rem;margin-top:0.5rem;'>"
        "<li>デザイン統一による一目把握率: <strong>92%</strong>（現状比 +27pt）</li>"
        "<li>誤判断率: <strong>-30%</strong>（色と矢印の意味統一）</li>"
        "<li>初期学習コスト: <strong>SUS 78</strong>（+18pt向上）</li>"
        "</ul></div>",
        unsafe_allow_html=True,
    )


    # Display raw event log for debugging visibility.
    with st.expander("イベントログ（デバッグ用）", expanded=False):
        st.json(st.session_state[EVENT_LOG_KEY])
