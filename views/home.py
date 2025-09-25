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


# --- Session defaults & constants ----------------------------------------------------

SESSION_KEYS: dict[str, str] = {
    "period": "今月",
    "store": "本店",
    "grain": "日次",
    "tab": "売上",
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
        .dashboard-kpi-row, .dashboard-filter-row {
            gap: 1rem;
        }
        .dashboard-kpi-row > div[data-testid="column"],
        .dashboard-filter-row > div[data-testid="column"] {
            min-width: 0 !important;
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
            div[data-testid="stDownloadButton"][data-key="floating_csv"] {
                position: fixed;
                right: 1.2rem;
                bottom: 1.2rem;
                z-index: 99;
                box-shadow: 0 6px 20px rgba(0,0,0,0.25);
            }
        }
        </style>
        """,
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
    """Render top KPI cards and the anomaly highlight area."""

    st.markdown('<div class="dashboard-kpi-row">', unsafe_allow_html=True)
    k1, k2, k3, k4 = st.columns((1, 1, 1, 1))
    with k1:
        st.metric("売上対予実差[%]", "+4.2", "+4.2%")
    with k2:
        st.metric("粗利率[%]", "32.1", "-0.8pt", delta_color="inverse")
    with k3:
        st.metric("資金残高[千円]", "12,300", "+320")
    with k4:
        st.markdown("#### 本日の異常検知")
        st.write("粗利率<30%のSKU 12件")
        st.caption("基準値は業種別中央値")
    st.markdown("</div>", unsafe_allow_html=True)
    st.caption(f"{ctx.period} / {ctx.store} / {ctx.grain} で集計")
    _log_event("view_alert", alert_type="gross_margin", count=12)


def _synthetic_dates(days: int) -> Iterable[str]:
    today = datetime.today()
    return [(today - timedelta(days=days - idx - 1)).strftime("%m/%d") for idx in range(days)]


def _render_trend_chart(title: str, data: pd.DataFrame, *, use_budget: bool = False) -> None:
    st.subheader(title)
    chart_df = data.set_index("index")
    if use_budget and "予算" in chart_df.columns:
        st.line_chart(chart_df[[c for c in chart_df.columns if c in ("実績", "予算")]], height=260)
    else:
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
    if highlights:
        styled = data.style.apply(lambda row: ["background-color: #ffe6e6" if "過多" in str(v) else "" for v in row], axis=1)
        st.dataframe(styled, hide_index=True, use_container_width=True)
    else:
        st.dataframe(data, hide_index=True, use_container_width=True)


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
        st.metric("売上", "+8.5%", "+8.5%")
    with c2:
        st.metric("進捗率", "74%", "-6pt", delta_color="inverse")
    with c3:
        st.metric("客単価[円]", "12,320", "+320")

    trend_df = pd.DataFrame(
        {
            "index": _synthetic_dates(10),
            "実績": [112, 118, 121, 134, 128, 139, 150, 154, 160, 168],
            "予算": [110, 115, 120, 130, 132, 136, 142, 148, 152, 158],
        }
    )
    _render_trend_chart("売上トレンド", trend_df, use_budget=True)

    bcols = st.columns(2)
    with bcols[0]:
        product_df = pd.DataFrame(
            {
                "項目": ["商品A", "商品B", "商品C", "商品D", "商品E"],
                "売上": [45, 42, 38, 32, 27],
            }
        )
        _render_breakdown_bars("商品TOP5", product_df)
    with bcols[1]:
        channel_df = pd.DataFrame(
            {
                "項目": ["店頭", "EC", "卸", "特販", "海外"],
                "売上": [60, 30, 18, 14, 10],
            }
        )
        _render_breakdown_bars("チャネルTOP5", channel_df)

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
        st.metric("粗利率[%]", "31.2", "-0.6pt", delta_color="inverse")
    with c2:
        st.metric("前月差[pt]", "-0.6", "-0.6pt", delta_color="inverse")
    with c3:
        st.metric("粗利額[千円]", "5,480", "-120", delta_color="inverse")

    margin_trend = pd.DataFrame(
        {
            "index": _synthetic_dates(10),
            "粗利率": [33.2, 32.8, 32.4, 32.1, 31.9, 31.6, 31.4, 31.2, 31.0, 30.8],
        }
    )
    _render_trend_chart("粗利率トレンド", margin_trend)

    bcols = st.columns(2)
    with bcols[0]:
        product_df = pd.DataFrame(
            {
                "項目": ["商品A", "商品B", "商品C", "商品D", "商品E"],
                "粗利[千円]": [210, 198, 184, 162, 150],
            }
        )
        _render_breakdown_bars("粗利悪化カテゴリTOP5", product_df)
    with bcols[1]:
        cause_df = pd.DataFrame(
            {
                "項目": ["値引", "仕入高騰", "構成変化", "在庫処分", "販促費"],
                "粗利影響": [-68, -54, -43, -32, -28],
            }
        )
        _render_breakdown_bars("差分要因TOP5", cause_df)

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
        st.metric("在庫金額[千円]", "23,400", "-1,200")
    with c2:
        st.metric("回転日数[日]", "45", "+5", delta_color="inverse")
    with c3:
        st.metric("欠品率[%]", "1.2", "-0.3pt")

    scatter_df = pd.DataFrame(
        {
            "index": ["SKU-001", "SKU-002", "SKU-003", "SKU-004", "SKU-005"],
            "在庫金額": [5400, 4600, 3800, 3200, 2800],
            "回転日数": [60, 52, 48, 38, 30],
        }
    )
    st.subheader("在庫散布図")
    st.scatter_chart(scatter_df.set_index("index"), x="在庫金額", y="回転日数", height=260)

    st.subheader("過多在庫SKU TOP20")
    overstock_df = pd.DataFrame(
        [
            {"SKU": "SKU-001", "在庫金額[千円]": 5400, "回転日数": 60, "状況": "過多"},
            {"SKU": "SKU-002", "在庫金額[千円]": 4600, "回転日数": 52, "状況": "過多"},
            {"SKU": "SKU-012", "在庫金額[千円]": 1800, "回転日数": 48, "状況": "注意"},
        ]
    )
    styled = overstock_df.style.applymap(
        lambda val: "background-color: #ffcccc" if val == "過多" else "",
        subset=["状況"],
    )
    st.dataframe(styled, hide_index=True, use_container_width=True)

    detail_df = pd.DataFrame(
        [
            {"SKU": "SKU-001", "在庫数": 1200, "在庫金額[千円]": 5400, "回転日数": 60, "販売予測": 400},
            {"SKU": "SKU-002", "在庫数": 900, "在庫金額[千円]": 4600, "回転日数": 52, "販売予測": 350},
            {"SKU": "SKU-003", "在庫数": 780, "在庫金額[千円]": 3800, "回転日数": 48, "販売予測": 300},
            {"SKU": "SKU-004", "在庫数": 620, "在庫金額[千円]": 3200, "回転日数": 38, "販売予測": 280},
        ]
    )
    _render_table("明細", detail_df, highlights=True)
    artifacts = _download_buttons("inventory", detail_df, enable_pdf=False)
    return artifacts


def _render_cash_tab(ctx: DashboardContext, *, active: bool) -> TabArtifacts:
    st.caption("指標: 営業CF[千円] / フリーCF[千円] / 資金残高[千円]")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("営業CF[千円]", "1,820", "+120")
    with c2:
        st.metric("フリーCF[千円]", "1,240", "+80")
    with c3:
        st.metric("月末残高[千円]", "12,300", "+320")

    cash_df = pd.DataFrame(
        {
            "index": _synthetic_dates(6),
            "入金": [620, 640, 580, 600, 650, 680],
            "出金": [-420, -450, -440, -430, -410, -405],
            "残高": [200, 230, 210, 230, 240, 275],
        }
    )
    _render_trend_chart("資金繰りトレンド", cash_df)

    st.subheader("今月末残高予測")
    st.area_chart(cash_df.set_index("index")[["残高"]], height=220)

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

    ctx = _render_filters()
    _render_home_summary(ctx)
    _log_event("view_home", period=ctx.period, store=ctx.store)

    st.markdown('<div class="dashboard-tabs">', unsafe_allow_html=True)
    previous_label = st.session_state.get("tab", TAB_LABELS[0])
    active_label = st.segmented_control(
        "指標タブ",
        TAB_LABELS,
        default=previous_label,
        key="primary_tab_selector",
        label_visibility="collapsed",
    )
    if active_label != previous_label:
        _log_event("switch_tab", tab_name=active_label)
    st.session_state["tab"] = active_label

    renderer = TAB_RENDERERS[active_label]
    current_artifacts = renderer(ctx, active=True)
    with st.expander(":grey_question: 用語集", expanded=False):
        st.markdown(
            """
            - **売上対予実差**: (実績−予算)/予算。
            - **粗利率**: 粗利÷売上。対前月をデフォルト比較。
            - **在庫回転日数**: 在庫÷日次売上。値が大きいほど悪化。
            - **営業CF**: 営業活動によるキャッシュフロー。
            """
        )
    st.markdown("</div>", unsafe_allow_html=True)

    # Floating CSV CTA for mobile
    st.download_button(
        "CSV",
        data=current_artifacts.csv_bytes or b"",
        file_name=f"{active_label}_detail.csv",
        key="floating_csv",
    )

    st.caption("取得に失敗した場合は接続/権限をご確認のうえ再試行してください。")

    # Display raw event log for debugging visibility.
    with st.expander("イベントログ（デバッグ用）", expanded=False):
        st.json(st.session_state[EVENT_LOG_KEY])
