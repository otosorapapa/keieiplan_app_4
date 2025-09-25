"""Streamlit home view for the phase-2 dashboard IA prototype."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO
from typing import Callable, Iterable

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

TAB_LABELS: list[str] = ["売上", "粗利", "在庫", "資金"]
PERIOD_OPTIONS = ["本日", "今週", "今月", "前年同月"]
STORE_OPTIONS = ["本店", "A店", "EC"]
GRAIN_OPTIONS = ["日次", "週次", "月次"]
EVENT_LOG_KEY = "_dashboard_events"

try:  # Streamlit 1.31+ exposes query_params; fall back gracefully otherwise.
    QUERY_PARAMS = st.query_params
except AttributeError:  # pragma: no cover - older versions simply lack this attr.
    QUERY_PARAMS = None

DEFAULT_STATE: dict[str, object] = {
    "period": "今月",
    "store": "本店",
    "grain": "日次",
    "tab": TAB_LABELS[0],
    "gmr_warn": 30.0,
    "turnover_bad": 40,
}

STATE_CASTERS: dict[str, callable] = {
    "period": str,
    "store": str,
    "grain": str,
    "tab": str,
    "gmr_warn": float,
    "turnover_bad": int,
}

STATUS_MESSAGES: dict[str, str] = {
    "empty": "該当データがありません。期間・店舗を変えて再実行してください。",
    "loading": "更新中… 最大3秒",
    "error": "取得に失敗しました。接続・権限をご確認のうえ再試行してください。",
}


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


@st.cache_data(ttl=60)
def fetch_sales_payload(period: str, store: str, grain: str) -> dict[str, pd.DataFrame]:
    trend_df = pd.DataFrame(
        {
            "index": _synthetic_dates(10),
            "実績[百万円]": [112, 118, 121, 134, 128, 139, 150, 154, 160, 168],
            "予算[百万円]": [110, 115, 120, 130, 132, 136, 142, 148, 152, 158],
        }
    )
    product_df = pd.DataFrame(
        {
            "項目": ["商品A", "商品B", "商品C", "商品D", "商品E"],
            "売上[千円]": [450, 420, 380, 320, 270],
        }
    )
    composition_df = pd.DataFrame(
        {
            "index": _synthetic_dates(6),
            "店頭[%]": [52, 51, 50, 49, 48, 47],
            "EC[%]": [28, 29, 30, 31, 32, 33],
            "卸[%]": [12, 12, 12, 12, 12, 12],
            "海外[%]": [8, 8, 8, 8, 8, 8],
        }
    )
    detail_df = pd.DataFrame(
        [
            {
                "日付": "10/01",
                "店舗": store,
                "商品": "商品A",
                "数量": 120,
                "売上[千円]": 540,
                "粗利[千円]": 168,
                "粗利率[%]": 31.1,
            },
            {
                "日付": "10/01",
                "店舗": store,
                "商品": "商品B",
                "数量": 95,
                "売上[千円]": 430,
                "粗利[千円]": 142,
                "粗利率[%]": 33.0,
            },
            {
                "日付": "10/02",
                "店舗": store,
                "商品": "商品C",
                "数量": 102,
                "売上[千円]": 408,
                "粗利[千円]": 128,
                "粗利率[%]": 31.4,
            },
            {
                "日付": "10/02",
                "店舗": store,
                "商品": "商品D",
                "数量": 88,
                "売上[千円]": 352,
                "粗利[千円]": 102,
                "粗利率[%]": 29.0,
            },
        ]
    )
    return {
        "trend": trend_df,
        "breakdown": product_df,
        "composition": composition_df,
        "detail": detail_df,
    }


@st.cache_data(ttl=60)
def fetch_margin_payload(period: str, store: str, grain: str) -> dict[str, pd.DataFrame]:
    margin_trend = pd.DataFrame(
        {
            "index": _synthetic_dates(10),
            "粗利率[%]": [33.2, 32.8, 32.4, 32.1, 31.9, 31.6, 31.4, 31.2, 31.0, 30.8],
        }
    )
    cause_df = pd.DataFrame(
        {
            "項目": ["値引", "仕入高騰", "構成変化", "在庫処分", "販促費"],
            "粗利影響[千円]": [-68, -54, -43, -32, -28],
        }
    )
    mix_df = pd.DataFrame(
        {
            "index": _synthetic_dates(6),
            "主力SKU[%]": [46, 45, 44, 44, 43, 42],
            "準主力SKU[%]": [32, 32, 33, 33, 34, 34],
            "新商品[%]": [12, 13, 13, 13, 13, 13],
            "長尾SKU[%]": [10, 10, 10, 10, 10, 11],
        }
    )
    detail_df = pd.DataFrame(
        [
            {
                "日付": "10/01",
                "商品": "商品A",
                "売上[千円]": 540,
                "粗利[千円]": 168,
                "粗利率[%]": 31.1,
                "対前月差[pt]": -0.5,
            },
            {
                "日付": "10/01",
                "商品": "商品B",
                "売上[千円]": 430,
                "粗利[千円]": 142,
                "粗利率[%]": 33.0,
                "対前月差[pt]": -0.6,
            },
            {
                "日付": "10/02",
                "商品": "商品C",
                "売上[千円]": 408,
                "粗利[千円]": 128,
                "粗利率[%]": 31.4,
                "対前月差[pt]": -0.7,
            },
            {
                "日付": "10/02",
                "商品": "商品D",
                "売上[千円]": 352,
                "粗利[千円]": 102,
                "粗利率[%]": 29.0,
                "対前月差[pt]": -0.8,
            },
        ]
    )
    return {
        "trend": margin_trend,
        "breakdown": cause_df,
        "mix": mix_df,
        "detail": detail_df,
    }


@st.cache_data(ttl=60)
def fetch_inventory_payload(period: str, store: str, grain: str) -> dict[str, pd.DataFrame]:
    inventory_trend = pd.DataFrame(
        {
            "index": _synthetic_dates(10),
            "在庫金額[百万円]": [26.4, 26.1, 25.8, 25.2, 24.8, 24.2, 23.9, 23.6, 23.4, 23.2],
        }
    )
    category_df = pd.DataFrame(
        {
            "項目": ["カテゴリA", "カテゴリB", "カテゴリC", "カテゴリD", "カテゴリE"],
            "在庫金額[千円]": [5200, 4800, 4100, 3600, 3200],
        }
    )
    coverage_df = pd.DataFrame(
        {
            "index": _synthetic_dates(6),
            "良品[%]": [64, 65, 65, 66, 67, 67],
            "滞留[%]": [18, 17, 17, 16, 15, 15],
            "欠品[%]": [6, 6, 6, 6, 6, 6],
            "廃棄予定[%]": [12, 12, 12, 12, 12, 12],
        }
    )
    detail_df = pd.DataFrame(
        [
            {
                "SKU": "SKU-001",
                "在庫数": 1200,
                "在庫金額[千円]": 5400,
                "回転日数[日]": 60,
                "販売予測": 400,
                "状況": "過多",
            },
            {
                "SKU": "SKU-002",
                "在庫数": 900,
                "在庫金額[千円]": 4600,
                "回転日数[日]": 52,
                "販売予測": 350,
                "状況": "過多",
            },
            {
                "SKU": "SKU-003",
                "在庫数": 780,
                "在庫金額[千円]": 3800,
                "回転日数[日]": 48,
                "販売予測": 300,
                "状況": "注意",
            },
            {
                "SKU": "SKU-004",
                "在庫数": 620,
                "在庫金額[千円]": 3200,
                "回転日数[日]": 38,
                "販売予測": 280,
                "状況": "注意",
            },
        ]
    )
    return {
        "trend": inventory_trend,
        "breakdown": category_df,
        "mix": coverage_df,
        "detail": detail_df,
    }


@st.cache_data(ttl=60)
def fetch_cash_payload(period: str, store: str, grain: str) -> dict[str, pd.DataFrame]:
    cash_df = pd.DataFrame(
        {
            "index": _synthetic_dates(6),
            "入金[百万円]": [62, 64, 58, 60, 65, 68],
            "出金[百万円]": [-42, -45, -44, -43, -41, -40],
            "残高[百万円]": [20, 23, 21, 23, 24, 27],
        }
    )
    flow_df = pd.DataFrame(
        {
            "項目": ["売掛回収", "在庫圧縮", "人件費", "投資支出", "販促費"],
            "キャッシュ影響[千円]": [680, 420, -520, -380, -260],
        }
    )
    balance_mix = pd.DataFrame(
        {
            "index": _synthetic_dates(6),
            "運転資金[%]": [58, 57, 56, 55, 54, 53],
            "投資資金[%]": [18, 19, 19, 19, 19, 20],
            "余剰資金[%]": [24, 24, 25, 26, 27, 27],
        }
    )
    detail_df = pd.DataFrame(
        [
            {"日付": "10/01", "入金[千円]": 620, "出金[千円]": 420, "営業CF[千円]": 200, "残高[千円]": 200},
            {"日付": "10/05", "入金[千円]": 640, "出金[千円]": 450, "営業CF[千円]": 190, "残高[千円]": 230},
            {"日付": "10/10", "入金[千円]": 580, "出金[千円]": 440, "営業CF[千円]": 140, "残高[千円]": 210},
            {"日付": "10/15", "入金[千円]": 600, "出金[千円]": 430, "営業CF[千円]": 170, "残高[千円]": 230},
        ]
    )
    return {
        "trend": cash_df,
        "breakdown": flow_df,
        "mix": balance_mix,
        "detail": detail_df,
    }


# --- Helpers ------------------------------------------------------------------------

def _coerce_value(key: str, value: object) -> object:
    """Cast raw values (usually strings) into their canonical type."""

    caster = STATE_CASTERS.get(key, lambda x: x)
    try:
        return caster(value)
    except Exception:  # pragma: no cover - guardrail for unexpected formats
        return DEFAULT_STATE[key]


def _ensure_session_defaults() -> None:
    """Ensure dashboard keys exist with query-param precedence."""

    for key, default in DEFAULT_STATE.items():
        if QUERY_PARAMS is not None and key in QUERY_PARAMS:
            st.session_state[key] = _coerce_value(key, QUERY_PARAMS[key])
        elif key not in st.session_state:
            st.session_state[key] = default

    st.session_state.setdefault("_last_values", {})

    if QUERY_PARAMS is None:
        st.session_state.setdefault("_qp_supported", False)
    else:
        st.session_state["_qp_supported"] = True

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


def _sync_query_params(**kwargs: object) -> None:
    """Sync persisted state to the URL if supported."""

    if QUERY_PARAMS is None:
        return

    sanitized = {key: str(value) for key, value in kwargs.items()}
    if sanitized:
        QUERY_PARAMS.update(**sanitized)


def _inject_responsive_styles() -> None:
    """Inject CSS for the <768px responsive breakpoints and helper styles."""

    token_styles = "\n".join(
        f"            --kp-{name}: {value};" for name, value in DESIGN_TOKENS.items()
    )

    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Source+Sans+3:wght@400;600&display=swap');
        :root {{
{token_styles}
        }}
        html, body, [class*="stApp"]  {{
            font-family: "Inter", "Source Sans 3", "Noto Sans JP", sans-serif;
            color: #1A1A1A;
            font-variant-numeric: tabular-nums;
        }}
        .dashboard-kpi-row, .dashboard-filter-row {{
            gap: 1.5rem;
        }}
        .dashboard-kpi-row > div[data-testid="column"],
        .dashboard-filter-row > div[data-testid="column"] {{
            min-width: 0 !important;
        }}
        .dashboard-kpi-row div[data-testid="metric-container"] {{
            background-color: var(--kp-card-bg);
            border-radius: 12px;
            padding: 1.25rem 1.5rem;
            box-shadow: 0 4px 12px rgba(11, 31, 59, 0.08);
            border: 1px solid rgba(11, 31, 59, 0.08);
        }}
        div[data-testid="metric-container"] label[data-testid="stMetricLabel"] {{
            color: var(--kp-secondary);
            font-weight: 600;
        }}
        div[data-testid="metric-container"] [data-testid="stMetricValue"] {{
            color: var(--kp-primary);
            font-size: 2rem;
        }}
        div[data-testid="metric-container"] [data-testid="stMetricDelta"] {{
            font-size: 0.95rem;
        }}
        .dashboard-tabs .stTabs [data-baseweb="tab"] {{
            background-color: transparent;
            border-bottom: 2px solid transparent;
            padding: 0.75rem 1rem;
            font-weight: 600;
            color: var(--kp-secondary);
        }}
        .dashboard-tabs .stTabs [aria-selected="true"] {{
            border-bottom-color: var(--kp-primary);
            color: var(--kp-primary);
        }}
        .dashboard-tabs .stTabs [data-baseweb="tab-list"] {{
            gap: 0.5rem;
        }}
        .dashboard-card {{
            background-color: var(--kp-card-bg);
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: 0 6px 16px rgba(11, 31, 59, 0.08);
            border: 1px solid rgba(11, 31, 59, 0.08);
        }}
        @media (max-width: 768px) {{
            .dashboard-kpi-row > div[data-testid="column"],
            .dashboard-filter-row > div[data-testid="column"] {{
                flex: 0 0 100% !important;
                width: 100% !important;
            }}
            .dashboard-tabs .stTabs {{
                overflow-x: auto;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_filters() -> DashboardContext:
    """Render the period/store/grain selectors and update session state."""

    def remember(key: str, value: object) -> None:
        st.session_state["_last_values"][key] = value

    def undo() -> None:
        last_snapshot = st.session_state.get("_last_values", {})
        if not last_snapshot:
            return
        for key, value in last_snapshot.items():
            st.session_state[key] = value
            widget_key = f"filter_{key}"
            if widget_key in st.session_state:
                st.session_state[widget_key] = value
        _sync_query_params(**last_snapshot)
        st.session_state["_last_values"] = {}
        _log_event("undo_filters", restored=last_snapshot)

    st.markdown('<div class="dashboard-filter-row">', unsafe_allow_html=True)
    f1, f2, f3 = st.columns(3)

    def _render_select(
        *,
        label: str,
        options: list[str],
        key: str,
        event_name: str,
    ) -> str:
        widget_key = f"filter_{key}"
        current_value = st.session_state[key]
        if current_value not in options:
            current_value = options[0]
            st.session_state[key] = current_value
        st.session_state.setdefault(widget_key, current_value)

        def _on_change() -> None:
            previous = st.session_state[key]
            current = st.session_state[widget_key]
            if current == previous:
                return
            remember(key, previous)
            st.session_state[key] = current
            _log_event(event_name, new_value=current)
            _sync_query_params(**{key: current})

        st.selectbox(
            label,
            options,
            index=options.index(st.session_state[key]),
            key=widget_key,
            on_change=_on_change,
        )
        return st.session_state[key]

    with f1:
        period = _render_select(
            label="期間",
            options=PERIOD_OPTIONS,
            key="period",
            event_name="select_period",
        )
    with f2:
        store = _render_select(
            label="店舗",
            options=STORE_OPTIONS,
            key="store",
            event_name="select_store",
        )
    with f3:
        grain = _render_select(
            label="粒度",
            options=GRAIN_OPTIONS,
            key="grain",
            event_name="select_grain",
        )
    st.markdown("</div>", unsafe_allow_html=True)

    st.button("直前に戻す", on_click=undo)

    return DashboardContext(period=period, store=store, grain=grain)


def _render_tab_selector() -> str:
    """Render the primary navigation tabs with URL/session persistence."""

    widget_key = "_tab_selector"
    st.session_state.setdefault(widget_key, st.session_state["tab"])

    def _on_change() -> None:
        previous = st.session_state["tab"]
        current = st.session_state[widget_key]
        if current == previous:
            return
        st.session_state["_last_values"]["tab"] = previous
        st.session_state["tab"] = current
        _log_event("switch_tab", tab=current)
        _sync_query_params(tab=current)

    st.markdown("<div class='sticky-tab-bar'>", unsafe_allow_html=True)
    selected = st.radio(
        "表示タブ",
        TAB_LABELS,
        index=TAB_LABELS.index(st.session_state["tab"]),
        key=widget_key,
        on_change=_on_change,
        horizontal=True,
        label_visibility="collapsed",
    )
    st.markdown("</div>", unsafe_allow_html=True)
    return selected


def _render_threshold_input(
    *, label: str, key: str, step: float, format: str, help_text: str | None = None
) -> float:
    """Render a persisted threshold input with undo/URL support."""

    widget_key = f"threshold_{key}"
    st.session_state.setdefault(widget_key, st.session_state[key])

    def _on_change() -> None:
        previous = st.session_state[key]
        current = st.session_state[widget_key]
        if current == previous:
            return
        st.session_state["_last_values"][key] = previous
        st.session_state[key] = current
        _log_event("set_threshold", name=key, value=current)
        _sync_query_params(**{key: current})

    st.number_input(
        label,
        value=st.session_state[key],
        step=step,
        format=format,
        key=widget_key,
        on_change=_on_change,
        help=help_text,
    )
    return float(st.session_state[key])


def _render_home_summary(ctx: DashboardContext) -> None:
    """Render top KPI cards based on the design tokens."""

    st.markdown('<div class="dashboard-kpi-row">', unsafe_allow_html=True)
    k1, k2, k3 = st.columns(3)
    with k1:
        st.metric("📈 売上対予実差[%]", "+4.2pt", "+0.8pt", delta_color="normal")
    with k2:
        st.metric("💹 粗利率[%]", "32.1%", "-0.8pt", delta_color="inverse")
    with k3:
        st.metric("💰 資金残高[千円]", "12,300千円", "+320千円", delta_color="normal")
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


def _with_data_loader(loader, ctx: DashboardContext) -> dict[str, pd.DataFrame] | None:
    """Execute data fetching with spinner, error handling and logging."""

    try:
        with st.spinner(STATUS_MESSAGES["loading"]):
            time.sleep(0.2)
            payload = loader(ctx.period, ctx.store, ctx.grain)
    except Exception as exc:  # pragma: no cover - visual feedback path
        st.error(STATUS_MESSAGES["error"])
        st.caption(f"technical: {type(exc).__name__}")
        st.button("再試行", on_click=lambda: st.rerun())
        _log_event("error_fetch", source=loader.__name__)
        return None

    if not payload:
        st.info(STATUS_MESSAGES["empty"])
        if st.button("再実行", key=f"retry_{loader.__name__}"):
            st.rerun()
        _log_event("empty_view", source=loader.__name__)
        return None

    return payload


def _render_table(
    title: str,
    data: pd.DataFrame,
    *,
    style_fn: Callable[[pd.Series], list[str]] | None = None,
) -> None:
    st.subheader(title)
    if data.empty:
        st.info(STATUS_MESSAGES["empty"])
        st.button("再実行", on_click=lambda: st.rerun())
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
    if style_fn is not None:
        dataframe = data.style.apply(style_fn, axis=1)
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
    file_name = f"{st.session_state['tab']}_{st.session_state['period']}.csv"
    with cols[0]:
        if st.download_button("CSVダウンロード", data=csv_bytes, file_name=file_name):
            _log_event("download_csv", tab_name=st.session_state["tab"], row_count=len(dataframe))
    if enable_pdf:
        pdf_bytes = _build_pdf_report(prefix, dataframe)
        with cols[1]:
            st.download_button(
                "PDFダウンロード",
                data=pdf_bytes,
                file_name=f"{st.session_state['tab']}_{st.session_state['period']}.pdf",
            )
    return TabArtifacts(detail_rows=len(dataframe), csv_bytes=csv_bytes)


def _render_sticky_cta(artifacts: TabArtifacts | None) -> None:
    """Render a floating CSV download CTA for mobile reach."""

    if artifacts is None or not artifacts.csv_bytes:
        return

    file_name = f"{st.session_state['tab']}_{st.session_state['period']}.csv"
    sticky = st.container()
    with sticky:
        st.markdown(
            "<div style='position:fixed; right:16px; bottom:16px; z-index:99;'>",
            unsafe_allow_html=True,
        )
        if st.download_button(
            "CSV", data=artifacts.csv_bytes, file_name=file_name, key="sticky_csv_cta"
        ):
            _log_event(
                "download_csv",
                tab_name=st.session_state["tab"],
                row_count=artifacts.detail_rows,
                origin="sticky",
            )
        st.markdown("</div>", unsafe_allow_html=True)


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

def _render_sales_tab(ctx: DashboardContext) -> TabArtifacts:
    st.caption("指標: 売上対予実差[%] / 進捗率[%] / 客単価[円]")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("売上対予実差[%]", "+8.5pt", "+1.2pt", delta_color="normal")
    with c2:
        st.metric("進捗率[%]", "74.0%", "-6.0pt", delta_color="inverse")
    with c3:
        st.metric("客単価[円]", "12,320円", "+320円", delta_color="normal")

    payload = _with_data_loader(fetch_sales_payload, ctx)
    if payload is None:
        return TabArtifacts(detail_rows=0, csv_bytes=b"")

    trend_col, breakdown_col = st.columns((3, 2))
    with trend_col:
        _render_trend_chart("売上トレンド", payload["trend"], use_budget=True)
    with breakdown_col:
        _render_breakdown_bars("商品売上TOP5[千円]", payload["breakdown"])

    st.subheader("チャネル構成比推移")
    st.area_chart(payload["composition"].set_index("index"), height=220)

    detail_df = payload["detail"].copy()
    _render_table("明細", detail_df)
    artifacts = _download_buttons("sales", detail_df, enable_pdf=True)
    return artifacts


def _render_margin_tab(ctx: DashboardContext) -> TabArtifacts:
    st.caption("指標: 粗利率[%] / 前月差[pt] / 粗利額[千円]")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("粗利率[%]", "31.2%", "-0.6pt", delta_color="inverse")
    with c2:
        st.metric("前月差[pt]", "-0.6pt", "-0.6pt", delta_color="inverse")
    with c3:
        st.metric("粗利額[千円]", "5,480千円", "-120千円", delta_color="inverse")

    gmr_warn = _render_threshold_input(
        label="粗利率の注意閾値[%]",
        key="gmr_warn",
        step=0.5,
        format="%.1f",
        help_text="この値未満のSKUが自動でハイライトされます。",
    )

    payload = _with_data_loader(fetch_margin_payload, ctx)
    if payload is None:
        return TabArtifacts(detail_rows=0, csv_bytes=b"")

    trend_col, breakdown_col = st.columns((3, 2))
    with trend_col:
        _render_trend_chart("粗利率トレンド", payload["trend"])
    with breakdown_col:
        _render_breakdown_bars("粗利悪化要因TOP5[千円]", payload["breakdown"])

    st.subheader("商品構成比推移")
    st.area_chart(payload["mix"].set_index("index"), height=220)

    detail_df = payload["detail"].copy()
    detail_df = detail_df.sort_values("粗利率[%]")

    def _highlight(row: pd.Series) -> list[str]:
        return ["background-color: #FFE8E8" if row.get("粗利率[%]", 100.0) < gmr_warn else "" for _ in row]

    _render_table("明細", detail_df, style_fn=_highlight)
    artifacts = _download_buttons("gross_margin", detail_df, enable_pdf=False)
    return artifacts


def _render_inventory_tab(ctx: DashboardContext) -> TabArtifacts:
    st.caption("指標: 在庫金額[千円] / 回転日数[日] / 欠品率[%]")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("在庫金額[千円]", "23,400千円", "-1,200千円", delta_color="inverse")
    with c2:
        st.metric("回転日数[日]", "45日", "+5日", delta_color="inverse")
    with c3:
        st.metric("欠品率[%]", "1.2%", "-0.3pt", delta_color="inverse")

    turnover_bad = _render_threshold_input(
        label="回転日数の警戒閾値[日]",
        key="turnover_bad",
        step=1.0,
        format="%.0f",
        help_text="この値を超えるSKUが自動でハイライトされます。",
    )

    payload = _with_data_loader(fetch_inventory_payload, ctx)
    if payload is None:
        return TabArtifacts(detail_rows=0, csv_bytes=b"")

    trend_col, breakdown_col = st.columns((3, 2))
    with trend_col:
        _render_trend_chart("在庫金額トレンド", payload["trend"])
    with breakdown_col:
        _render_breakdown_bars("滞留カテゴリTOP5[千円]", payload["breakdown"])

    st.subheader("在庫区分構成比推移")
    st.area_chart(payload["mix"].set_index("index"), height=220)

    detail_df = payload["detail"].copy()
    detail_df = detail_df.sort_values("回転日数[日]", ascending=False)

    def _highlight(row: pd.Series) -> list[str]:
        return [
            "background-color: #FFE8E8" if row.get("回転日数[日]", 0) > turnover_bad else ""
            for _ in row
        ]

    _render_table("明細", detail_df, style_fn=_highlight)
    artifacts = _download_buttons("inventory", detail_df, enable_pdf=False)
    return artifacts


def _render_cash_tab(ctx: DashboardContext) -> TabArtifacts:
    st.caption("指標: 営業CF[千円] / フリーCF[千円] / 資金残高[千円]")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("営業CF[千円]", "1,820千円", "+120千円", delta_color="normal")
    with c2:
        st.metric("フリーCF[千円]", "1,240千円", "+80千円", delta_color="normal")
    with c3:
        st.metric("月末残高[千円]", "12,300千円", "+320千円", delta_color="normal")

    payload = _with_data_loader(fetch_cash_payload, ctx)
    if payload is None:
        return TabArtifacts(detail_rows=0, csv_bytes=b"")

    trend_col, breakdown_col = st.columns((3, 2))
    with trend_col:
        _render_trend_chart("資金繰りトレンド", payload["trend"])
    with breakdown_col:
        _render_breakdown_bars("資金流入出TOP5[千円]", payload["breakdown"])

    st.subheader("資金構成比推移")
    st.area_chart(payload["mix"].set_index("index"), height=220)

    detail_df = payload["detail"].copy()
    _render_table("明細", detail_df)
    artifacts = _download_buttons("cash", detail_df, enable_pdf=False)
    return artifacts


# --- Public entrypoint --------------------------------------------------------------

TAB_RENDERERS = {
    "売上": _render_sales_tab,
    "粗利": _render_margin_tab,
    "在庫": _render_inventory_tab,
    "資金": _render_cash_tab,
}

PAYLOAD_LOADERS = {
    "売上": fetch_sales_payload,
    "粗利": fetch_margin_payload,
    "在庫": fetch_inventory_payload,
    "資金": fetch_cash_payload,
}


def render_home_page() -> None:
    """Render the redesigned dashboard home following the IA specification."""

    _ensure_session_defaults()
    _inject_responsive_styles()

    st.title("経営ダッシュボード")
    st.caption("KGI直結の指標を一目で把握し、3クリック以内で深掘りできるホーム画面")

    filters_container = st.container()
    with filters_container:
        ctx = _render_filters()

    selected_tab = _render_tab_selector()

    summary_placeholder = st.container()
    with summary_placeholder:
        _render_home_summary(ctx)
        _log_event("view_top", period=ctx.period, store=ctx.store)

    _log_event("view_home", period=ctx.period, store=ctx.store)

    artifacts = TAB_RENDERERS[selected_tab](ctx)
    _render_sticky_cta(artifacts)

    counts_summary = " / ".join(
        f"{label}: {len(loader(ctx.period, ctx.store, ctx.grain)['detail'])}件"
        for label, loader in PAYLOAD_LOADERS.items()
    )
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
