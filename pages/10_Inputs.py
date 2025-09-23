"""Input hub for sales, costs, investments, borrowings and tax policy."""
from __future__ import annotations

import io
import json
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Mapping, Tuple

import altair as alt
import pandas as pd
import streamlit as st

from formatting import UNIT_FACTORS, format_amount_with_unit, format_ratio
from models import (
    DEFAULT_CAPEX_PLAN,
    DEFAULT_COST_PLAN,
    DEFAULT_LOAN_SCHEDULE,
    DEFAULT_SALES_PLAN,
    DEFAULT_TAX_POLICY,
    INDUSTRY_TEMPLATES,
    MONTH_SEQUENCE,
    EstimateRange,
    CapexPlan,
    LoanSchedule,
    TaxPolicy,
)
from calc import compute, generate_cash_flow, plan_from_models
from pydantic import ValidationError
from state import ensure_session_defaults
from services import auth
from services.auth import AuthError
from services.fermi_learning import range_profile_from_estimate, update_learning_state
from services.marketing_strategy import (
    FOUR_P_KEYS,
    FOUR_P_LABELS,
    SESSION_STATE_KEY as MARKETING_STRATEGY_KEY,
    empty_marketing_state,
    generate_marketing_recommendations,
    marketing_state_has_content,
)
from theme import inject_theme
from ui.components import render_callout
from validators import ValidationIssue, validate_bundle
from ui.streamlit_compat import use_container_width_kwargs
from ui.fermi import FERMI_SEASONAL_PATTERNS, compute_fermi_estimate

st.set_page_config(
    page_title="経営計画スタジオ｜Inputs",
    page_icon="✎",
    layout="wide",
)

inject_theme()
ensure_session_defaults()

finance_raw: Dict[str, Dict] = st.session_state.get("finance_raw", {})
if not finance_raw:
    finance_raw = {
        "sales": DEFAULT_SALES_PLAN.model_dump(),
        "costs": DEFAULT_COST_PLAN.model_dump(),
        "capex": DEFAULT_CAPEX_PLAN.model_dump(),
        "loans": DEFAULT_LOAN_SCHEDULE.model_dump(),
        "tax": DEFAULT_TAX_POLICY.model_dump(),
    }
    st.session_state["finance_raw"] = finance_raw

validation_errors: List[ValidationIssue] = st.session_state.get("finance_validation_errors", [])


MONTH_COLUMNS = [f"月{m:02d}" for m in MONTH_SEQUENCE]
ASSUMPTION_NUMERIC_COLUMNS = ["想定顧客数", "客単価", "購入頻度(月)"]
ASSUMPTION_RANGE_COLUMNS = ["年間売上(最低)", "年間売上(中央値)", "年間売上(最高)"]
ASSUMPTION_TEXT_COLUMNS = ["メモ"]
ASSUMPTION_COLUMNS = [
    *ASSUMPTION_NUMERIC_COLUMNS,
    *ASSUMPTION_RANGE_COLUMNS,
    *ASSUMPTION_TEXT_COLUMNS,
]
REQUIRED_TEXT_TEMPLATE_COLUMNS = ["チャネル", "商品"]
REQUIRED_NUMERIC_TEMPLATE_COLUMNS = [*ASSUMPTION_NUMERIC_COLUMNS]
REQUIRED_TEMPLATE_COLUMNS = [
    *REQUIRED_TEXT_TEMPLATE_COLUMNS,
    *REQUIRED_NUMERIC_TEMPLATE_COLUMNS,
    *MONTH_COLUMNS,
]
TEMPLATE_COLUMN_GUIDE = [
    ("チャネル", "販売経路（例：オンライン、店舗など）。"),
    ("商品", "チャネル内の主力商品・サービス名。"),
    ("想定顧客数", "1か月に想定する顧客数。整数または小数で入力します。"),
    ("客単価", "税込の平均単価（円）。カンマなしの半角数値で入力します。"),
    ("購入頻度(月)", "1か月あたりの購入回数。サブスクは1.0が基準です。"),
    (
        "年間売上(最低/中央値/最高)",
        "任意入力。シナリオ比較用のレンジで、空欄は0として扱います。",
    ),
    (
        f"月01〜月{MONTH_SEQUENCE[-1]:02d}",
        "各月の売上金額（円）。未使用の月は0を入力してください。",
    ),
    ("メモ", "任意の補足メモ。獲得施策や前提条件を記録できます。"),
]
SALES_TEMPLATE_STATE_KEY = "sales_template_df"
SALES_CHANNEL_COUNTER_KEY = "sales_channel_counter"
SALES_PRODUCT_COUNTER_KEY = "sales_product_counter"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_MIME_TYPES = {
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
ALLOWED_EXTENSIONS = {".csv", ".xlsx"}

INPUT_WIZARD_STEP_KEY = "input_wizard_step"
BUSINESS_CONTEXT_KEY = "business_context"
INDUSTRY_TEMPLATE_KEY = "selected_industry_template"

FERMI_RESULT_STATE_KEY = "fermi_last_estimate"
COST_RANGE_STATE_KEY = "cost_range_profiles"
FINANCIAL_SERIES_STATE_KEY = "financial_timeseries"
FINANCIAL_CATEGORY_OPTIONS = ("実績", "計画")
FINANCIAL_SERIES_COLUMNS = [
    "年度",
    "区分",
    "売上高",
    "粗利益率",
    "営業利益率",
    "固定費",
    "変動費",
    "設備投資額",
    "借入残高",
    "減価償却費",
    "総資産",
]
FINANCIAL_SERIES_NUMERIC_COLUMNS = [
    "売上高",
    "粗利益率",
    "営業利益率",
    "固定費",
    "変動費",
    "設備投資額",
    "借入残高",
    "減価償却費",
    "総資産",
]

WIZARD_STEPS = [
    {
        "id": "context",
        "title": "ビジネスモデル整理",
        "description": "3C分析・ビジネスモデルキャンバス・SWOT/PESTで事業環境を整理します。",
    },
    {
        "id": "sales",
        "title": "売上計画",
        "description": "チャネル×商品×月で売上を想定し、季節性や販促を織り込みます。",
    },
    {
        "id": "costs",
        "title": "原価・経費",
        "description": "粗利益率を意識しながら変動費・固定費・営業外項目を整理します。",
    },
    {
        "id": "invest",
        "title": "投資・借入",
        "description": "成長投資と資金調達のスケジュールを設定します。",
    },
    {
        "id": "tax",
        "title": "税制・保存",
        "description": "税率と最終チェックを行い、入力内容を保存します。",
    },
]

BUSINESS_CONTEXT_TEMPLATE = {
    "three_c_customer": "",
    "three_c_company": "",
    "three_c_competitor": "",
    "bmc_customer_segments": "",
    "bmc_value_proposition": "",
    "bmc_channels": "",
    "qualitative_memo": "",
}

BUSINESS_CONTEXT_PLACEHOLDER = {
    "three_c_customer": "主要顧客やターゲット市場の概要",
    "three_c_company": "自社の強み・差別化要素",
    "three_c_competitor": "競合の特徴と比較ポイント",
    "bmc_customer_segments": "顧客セグメントの詳細像 (例：30代共働き世帯、法人経理部門など)",
    "bmc_value_proposition": "提供価値・顧客の課題解決方法 (例：在庫管理を自動化し月30時間削減)",
    "bmc_channels": "顧客に価値を届けるチャネル (例：ECサイト、代理店、直販営業)",
    "qualitative_memo": "事業計画書に記載したい補足・KGI/KPIの背景",
}

STRATEGIC_ANALYSIS_KEY = "strategic_analysis"
MARKETING_STRATEGY_SNAPSHOT_KEY = "marketing_strategy_snapshot"
SWOT_CATEGORY_OPTIONS = ("強み", "弱み", "機会", "脅威")
PEST_DIMENSION_OPTIONS = ("政治", "経済", "社会", "技術")
PEST_DIRECTION_OPTIONS = ("機会", "脅威")
SWOT_EDITOR_COLUMNS = ("分類", "要因", "重要度(1-5)", "確度(1-5)", "備考")
PEST_EDITOR_COLUMNS = (
    "区分",
    "要因",
    "影響方向",
    "影響度(1-5)",
    "確度(1-5)",
    "備考",
)
DEFAULT_SWOT_EDITOR_ROWS = [
    {"分類": "強み", "要因": "", "重要度(1-5)": 3.0, "確度(1-5)": 3.0, "備考": ""},
    {"分類": "弱み", "要因": "", "重要度(1-5)": 3.0, "確度(1-5)": 3.0, "備考": ""},
    {"分類": "機会", "要因": "", "重要度(1-5)": 3.0, "確度(1-5)": 3.0, "備考": ""},
    {"分類": "脅威", "要因": "", "重要度(1-5)": 3.0, "確度(1-5)": 3.0, "備考": ""},
]
DEFAULT_PEST_EDITOR_ROWS = [
    {"区分": "政治", "要因": "", "影響方向": "機会", "影響度(1-5)": 3.0, "確度(1-5)": 3.0, "備考": ""},
    {"区分": "経済", "要因": "", "影響方向": "機会", "影響度(1-5)": 3.0, "確度(1-5)": 3.0, "備考": ""},
    {"区分": "社会", "要因": "", "影響方向": "機会", "影響度(1-5)": 3.0, "確度(1-5)": 3.0, "備考": ""},
    {"区分": "技術", "要因": "", "影響方向": "機会", "影響度(1-5)": 3.0, "確度(1-5)": 3.0, "備考": ""},
]

FOUR_P_INPUT_GUIDE = {
    "product": {
        "current": "例：SaaS型在庫管理と分析ダッシュボードを提供し、導入支援を標準化。",
        "challenge": "例：業種別要件への対応が遅く、アップセルが伸びない。",
        "metric": "例：年間解約率5%以下、NPS+30を目標。",
    },
    "price": {
        "current": "例：月額12,000円/アカウント。初期費用は5万円。",
        "challenge": "例：価格が高いとの指摘が多く、値引き依存が続く。",
        "metric": "例：LTV/CAC 3.0倍、平均受注単価11,000円維持。",
    },
    "place": {
        "current": "例：直販営業とECサイトで全国提供。代理店は2社。",
        "challenge": "例：地方での導入サポート網が不足。",
        "metric": "例：チャネル別CVR5%、平均リードタイム30日。",
    },
    "promotion": {
        "current": "例：ウェビナーとデジタル広告、展示会出展を実施。",
        "challenge": "例：リード獲得単価が高止まりしている。",
        "metric": "例：月間リード数120件、SQL化率25%。",
    },
}

MARKETING_CUSTOMER_PLACEHOLDER = {
    "needs": "市場ニーズや顧客課題（例：属人的な在庫管理から脱却したい）",
    "segments": "顧客セグメント（例：年商5〜10億円の製造業、飲食チェーンなど）",
    "persona": "ターゲット顧客のペルソナ（例：工場長、店舗オーナー、経理責任者）",
}

MARKETING_COMPANY_PLACEHOLDER = {
    "strengths": "自社の強み・差別化資源（例：専門コンサルチーム、独自AIエンジン）",
    "weaknesses": "弱み・制約（例：営業人員が不足、知名度が低い）",
    "resources": "活用できるリソースやパートナー（例：地域金融機関との協業）",
}

MARKETING_COMPETITOR_HELP = (
    "業界トップ企業と地元企業を比較し、平均価格やサービス差別化ポイントを数値で入力し"
    "てください。サービス差別化スコアは1（低い）〜5（高い）で評価します。"
)

CUSTOMER_EXAMPLE_TEXT = (
    "例：主要顧客やターゲット市場の概要｜年商5〜10億円規模の製造業の経営企画部門。"
    "紙の在庫管理からDX移行を検討しており、月次で意思決定できるダッシュボードを求めている。"
)

BUSINESS_CONTEXT_SNAPSHOT_KEY = "business_context_snapshot"
BUSINESS_CONTEXT_LAST_SAVED_KEY = "business_context_last_saved_at"


def _default_financial_timeseries(fiscal_year: int) -> pd.DataFrame:
    """Return a template dataframe for 3年実績 + 5年計画."""

    records: List[Dict[str, object]] = []
    start_year = fiscal_year - 3
    for offset in range(8):
        year = start_year + offset
        category = "実績" if year < fiscal_year else "計画"
        record: Dict[str, object] = {
            "年度": int(year),
            "区分": category,
        }
        for column in FINANCIAL_SERIES_NUMERIC_COLUMNS:
            record[column] = 0.0
        records.append(record)
    return pd.DataFrame(records, columns=FINANCIAL_SERIES_COLUMNS)


def _load_financial_timeseries_df(fiscal_year: int) -> pd.DataFrame:
    """Load the financial time-series editor dataframe from session state."""

    stored_state: Dict[str, object] = st.session_state.get(FINANCIAL_SERIES_STATE_KEY, {})
    records = stored_state.get("records") if isinstance(stored_state, dict) else None
    if isinstance(records, list) and records:
        df = pd.DataFrame(records)
    else:
        df = _default_financial_timeseries(fiscal_year)

    df = df.copy()
    if "年度" not in df.columns:
        df["年度"] = [fiscal_year - 3 + idx for idx in range(len(df))]
    df["年度"] = pd.to_numeric(df["年度"], errors="coerce").fillna(fiscal_year).astype(int)

    if "区分" not in df.columns:
        df["区分"] = ["実績" if year < fiscal_year else "計画" for year in df["年度"]]
    else:
        categories: List[str] = []
        for raw, year in zip(df["区分"], df["年度"]):
            label = str(raw).strip()
            if label not in FINANCIAL_CATEGORY_OPTIONS:
                label = "実績" if year <= fiscal_year - 1 else "計画"
            categories.append(label)
        df["区分"] = categories

    for column in FINANCIAL_SERIES_COLUMNS:
        if column not in df.columns:
            if column in FINANCIAL_SERIES_NUMERIC_COLUMNS:
                df[column] = 0.0
            elif column == "年度":
                continue
            else:
                df[column] = ""

    for column in FINANCIAL_SERIES_NUMERIC_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)

    category_order = {label: index for index, label in enumerate(FINANCIAL_CATEGORY_OPTIONS)}
    df["_category_order"] = df["区分"].map(category_order).fillna(0)
    df = (
        df[FINANCIAL_SERIES_COLUMNS + ["_category_order"]]
        .sort_values(["年度", "_category_order"])
        .drop(columns="_category_order")
        .reset_index(drop=True)
    )
    return df


def _persist_financial_timeseries(df: pd.DataFrame, fiscal_year: int) -> None:
    """Store the edited financial time-series dataframe back to session state."""

    sanitized = df.copy()
    if "年度" not in sanitized.columns:
        sanitized["年度"] = [fiscal_year for _ in range(len(sanitized))]
    sanitized["年度"] = pd.to_numeric(sanitized["年度"], errors="coerce").fillna(fiscal_year).astype(int)

    if "区分" not in sanitized.columns:
        sanitized["区分"] = ["実績" if year <= fiscal_year - 1 else "計画" for year in sanitized["年度"]]
    else:
        sanitized["区分"] = [
            str(value).strip() if str(value).strip() in FINANCIAL_CATEGORY_OPTIONS else ("実績" if year <= fiscal_year - 1 else "計画")
            for value, year in zip(sanitized["区分"], sanitized["年度"])
        ]

    for column in FINANCIAL_SERIES_NUMERIC_COLUMNS:
        sanitized[column] = pd.to_numeric(sanitized.get(column, 0.0), errors="coerce").fillna(0.0)

    records: List[Dict[str, object]] = []
    for _, row in sanitized.iterrows():
        record: Dict[str, object] = {
            "年度": int(row["年度"]),
            "区分": str(row["区分"]),
        }
        for column in FINANCIAL_SERIES_NUMERIC_COLUMNS:
            value = float(row[column]) if pd.notna(row[column]) else 0.0
            record[column] = value
        records.append(record)

    st.session_state[FINANCIAL_SERIES_STATE_KEY] = {
        "records": records,
        "base_year": int(fiscal_year),
    }


def _swot_editor_dataframe_from_state(records: List[Dict[str, object]] | None) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(DEFAULT_SWOT_EDITOR_ROWS, columns=SWOT_EDITOR_COLUMNS)

    rows: List[Dict[str, object]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        category = str(record.get("category", "")) or SWOT_CATEGORY_OPTIONS[0]
        if category not in SWOT_CATEGORY_OPTIONS:
            category = SWOT_CATEGORY_OPTIONS[0]
        try:
            impact = float(record.get("impact", 3.0))
        except (TypeError, ValueError):
            impact = 3.0
        try:
            probability = float(record.get("probability", 3.0))
        except (TypeError, ValueError):
            probability = 3.0
        rows.append(
            {
                "分類": category,
                "要因": str(record.get("factor", "")),
                "重要度(1-5)": impact,
                "確度(1-5)": probability,
                "備考": str(record.get("note", "")),
            }
        )

    if not rows:
        return pd.DataFrame(DEFAULT_SWOT_EDITOR_ROWS, columns=SWOT_EDITOR_COLUMNS)

    df = pd.DataFrame(rows)
    for column in SWOT_EDITOR_COLUMNS:
        if column not in df.columns:
            df[column] = "" if column in ("分類", "要因", "備考") else 3.0
    return df[SWOT_EDITOR_COLUMNS].copy()


def _pest_editor_dataframe_from_state(records: List[Dict[str, object]] | None) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(DEFAULT_PEST_EDITOR_ROWS, columns=PEST_EDITOR_COLUMNS)

    rows: List[Dict[str, object]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        dimension = str(record.get("dimension", "")) or PEST_DIMENSION_OPTIONS[0]
        if dimension not in PEST_DIMENSION_OPTIONS:
            dimension = PEST_DIMENSION_OPTIONS[0]
        direction = str(record.get("direction", "")) or PEST_DIRECTION_OPTIONS[0]
        if direction not in PEST_DIRECTION_OPTIONS:
            direction = PEST_DIRECTION_OPTIONS[0]
        try:
            impact = float(record.get("impact", 3.0))
        except (TypeError, ValueError):
            impact = 3.0
        try:
            probability = float(record.get("probability", 3.0))
        except (TypeError, ValueError):
            probability = 3.0
        rows.append(
            {
                "区分": dimension,
                "要因": str(record.get("factor", "")),
                "影響方向": direction,
                "影響度(1-5)": impact,
                "確度(1-5)": probability,
                "備考": str(record.get("note", "")),
            }
        )

    if not rows:
        return pd.DataFrame(DEFAULT_PEST_EDITOR_ROWS, columns=PEST_EDITOR_COLUMNS)

    df = pd.DataFrame(rows)
    for column in PEST_EDITOR_COLUMNS:
        if column not in df.columns:
            df[column] = "" if column in ("区分", "要因", "影響方向", "備考") else 3.0
    return df[PEST_EDITOR_COLUMNS].copy()


def _records_from_swot_editor(df: pd.DataFrame) -> List[Dict[str, object]]:
    if df is None or df.empty:
        return []

    sanitized = df.copy()
    for column in SWOT_EDITOR_COLUMNS:
        if column not in sanitized.columns:
            sanitized[column] = "" if column in ("分類", "要因", "備考") else 3.0

    sanitized["分類"] = [
        value if str(value) in SWOT_CATEGORY_OPTIONS else SWOT_CATEGORY_OPTIONS[0]
        for value in sanitized["分類"]
    ]
    sanitized["要因"] = sanitized["要因"].fillna("").astype(str).str.strip()
    sanitized["備考"] = sanitized["備考"].fillna("").astype(str)
    sanitized["重要度(1-5)"] = (
        pd.to_numeric(sanitized["重要度(1-5)"], errors="coerce")
        .fillna(3.0)
        .clip(1.0, 5.0)
    )
    sanitized["確度(1-5)"] = (
        pd.to_numeric(sanitized["確度(1-5)"], errors="coerce")
        .fillna(3.0)
        .clip(1.0, 5.0)
    )

    records: List[Dict[str, object]] = []
    for _, row in sanitized.iterrows():
        factor = str(row["要因"]).strip()
        if not factor:
            continue
        records.append(
            {
                "category": str(row["分類"]),
                "factor": factor,
                "impact": float(row["重要度(1-5)"]),
                "probability": float(row["確度(1-5)"]),
                "note": str(row["備考"]),
            }
        )
    return records


def _records_from_pest_editor(df: pd.DataFrame) -> List[Dict[str, object]]:
    if df is None or df.empty:
        return []

    sanitized = df.copy()
    for column in PEST_EDITOR_COLUMNS:
        if column not in sanitized.columns:
            sanitized[column] = "" if column in ("区分", "要因", "影響方向", "備考") else 3.0

    sanitized["区分"] = [
        value if str(value) in PEST_DIMENSION_OPTIONS else PEST_DIMENSION_OPTIONS[0]
        for value in sanitized["区分"]
    ]
    sanitized["影響方向"] = [
        value if str(value) in PEST_DIRECTION_OPTIONS else PEST_DIRECTION_OPTIONS[0]
        for value in sanitized["影響方向"]
    ]
    sanitized["要因"] = sanitized["要因"].fillna("").astype(str).str.strip()
    sanitized["備考"] = sanitized["備考"].fillna("").astype(str)
    sanitized["影響度(1-5)"] = (
        pd.to_numeric(sanitized["影響度(1-5)"], errors="coerce")
        .fillna(3.0)
        .clip(1.0, 5.0)
    )
    sanitized["確度(1-5)"] = (
        pd.to_numeric(sanitized["確度(1-5)"], errors="coerce")
        .fillna(3.0)
        .clip(1.0, 5.0)
    )

    records: List[Dict[str, object]] = []
    for _, row in sanitized.iterrows():
        factor = str(row["要因"]).strip()
        if not factor:
            continue
        records.append(
            {
                "dimension": str(row["区分"]),
                "factor": factor,
                "direction": str(row["影響方向"]),
                "impact": float(row["影響度(1-5)"]),
                "probability": float(row["確度(1-5)"]),
                "note": str(row["備考"]),
            }
        )
    return records


def _build_snapshot_payload() -> Dict[str, object]:
    """Collect the current session state into a serialisable snapshot."""

    snapshot: Dict[str, object] = {
        "finance_raw": st.session_state.get("finance_raw", {}),
        "finance_settings": st.session_state.get("finance_settings", {}),
        "scenarios": st.session_state.get("scenarios", []),
        "working_capital_profile": st.session_state.get("working_capital_profile", {}),
        "what_if_scenarios": st.session_state.get("what_if_scenarios", {}),
        "business_context": st.session_state.get(BUSINESS_CONTEXT_KEY, {}),
        "financial_timeseries": st.session_state.get(FINANCIAL_SERIES_STATE_KEY, {}),
        "strategic_analysis": st.session_state.get(STRATEGIC_ANALYSIS_KEY, {}),
        "marketing_strategy": st.session_state.get(MARKETING_STRATEGY_KEY, {}),
        "generated_at": datetime.utcnow().isoformat(),
    }
    scenario_df_state = st.session_state.get("scenario_df")
    if isinstance(scenario_df_state, pd.DataFrame):
        snapshot["scenario_df"] = scenario_df_state.to_dict(orient="records")
    elif scenario_df_state is not None:
        snapshot["scenario_df"] = scenario_df_state
    return snapshot


def _hydrate_snapshot(snapshot: Dict[str, object]) -> bool:
    """Load a snapshot dictionary back into Streamlit session state."""

    finance_raw_data = snapshot.get("finance_raw")
    if not isinstance(finance_raw_data, dict):
        st.error("保存データの形式が正しくありません。")
        return False
    bundle, issues = validate_bundle(finance_raw_data)
    if issues:
        st.session_state["finance_validation_errors"] = issues
        st.error("保存データの検証に失敗しました。入力項目をご確認ください。")
        return False
    st.session_state["finance_raw"] = finance_raw_data
    st.session_state["finance_models"] = {
        "sales": bundle.sales,
        "costs": bundle.costs,
        "capex": bundle.capex,
        "loans": bundle.loans,
        "tax": bundle.tax,
    }
    st.session_state["finance_validation_errors"] = []
    if "finance_settings" in snapshot and isinstance(snapshot["finance_settings"], dict):
        st.session_state["finance_settings"] = snapshot["finance_settings"]
    if "working_capital_profile" in snapshot and isinstance(snapshot["working_capital_profile"], dict):
        st.session_state["working_capital_profile"] = snapshot["working_capital_profile"]
    if "scenarios" in snapshot and isinstance(snapshot["scenarios"], list):
        st.session_state["scenarios"] = snapshot["scenarios"]
    scenario_df_state = snapshot.get("scenario_df")
    if isinstance(scenario_df_state, list):
        st.session_state["scenario_df"] = pd.DataFrame(scenario_df_state)
    elif isinstance(scenario_df_state, dict):
        st.session_state["scenario_df"] = pd.DataFrame(scenario_df_state)
    if "business_context" in snapshot and isinstance(snapshot["business_context"], dict):
        st.session_state[BUSINESS_CONTEXT_KEY] = snapshot["business_context"]
    if "financial_timeseries" in snapshot and isinstance(snapshot["financial_timeseries"], dict):
        st.session_state[FINANCIAL_SERIES_STATE_KEY] = snapshot["financial_timeseries"]
    if "strategic_analysis" in snapshot and isinstance(snapshot["strategic_analysis"], dict):
        strategic_snapshot = snapshot["strategic_analysis"]
        swot_records = strategic_snapshot.get("swot") if isinstance(strategic_snapshot.get("swot"), list) else []
        pest_records = strategic_snapshot.get("pest") if isinstance(strategic_snapshot.get("pest"), list) else []
        st.session_state[STRATEGIC_ANALYSIS_KEY] = {
            "swot": swot_records,
            "pest": pest_records,
        }
        st.session_state["swot_editor_df"] = _swot_editor_dataframe_from_state(swot_records)
        st.session_state["pest_editor_df"] = _pest_editor_dataframe_from_state(pest_records)
    if "marketing_strategy" in snapshot and isinstance(snapshot["marketing_strategy"], dict):
        marketing_snapshot = deepcopy(snapshot["marketing_strategy"])
        _ensure_nested_dict(marketing_snapshot, empty_marketing_state())
        st.session_state[MARKETING_STRATEGY_KEY] = marketing_snapshot
    return True


def _ensure_cost_range_state(
    range_defaults: Dict[str, object],
    *,
    variable_defaults: Dict[str, object],
    fixed_defaults: Dict[str, object],
    noi_defaults: Dict[str, object],
    noe_defaults: Dict[str, object],
    unit_factor: Decimal,
) -> None:
    state: Dict[str, Dict[str, float]] = st.session_state.get(COST_RANGE_STATE_KEY, {})
    if not isinstance(state, dict):
        state = {}

    def _profile_from_defaults(code: str, defaults: Dict[str, object], divisor: Decimal) -> Dict[str, float]:
        base = Decimal(str(defaults.get(code, 0.0)))
        divisor = divisor or Decimal("1")
        base_value = float(base / divisor)
        return {"min": base_value, "typical": base_value, "max": base_value}

    combined_defaults = {
        **{code: (variable_defaults.get(code, 0.0), Decimal("1")) for code in VARIABLE_RATIO_CODES},
        **{code: (fixed_defaults.get(code, 0.0), unit_factor) for code in FIXED_COST_CODES},
        **{code: (noi_defaults.get(code, 0.0), unit_factor) for code in NOI_CODES},
        **{code: (noe_defaults.get(code, 0.0), unit_factor) for code in NOE_CODES},
    }

    for code, (default_value, divisor) in combined_defaults.items():
        if code in range_defaults:
            raw = range_defaults[code]
            if isinstance(raw, EstimateRange):
                profile = range_profile_from_estimate(raw, divisor)
            elif isinstance(raw, dict):
                profile = range_profile_from_estimate(EstimateRange(**raw), divisor)
            else:  # pragma: no cover - defensive
                profile = _profile_from_defaults(code, {code: default_value}, divisor)
        else:
            profile = _profile_from_defaults(code, {code: default_value}, divisor)
        if code not in state:
            state[code] = profile
    st.session_state[COST_RANGE_STATE_KEY] = state


def _update_cost_range_state_from_editor(updated: pd.DataFrame) -> None:
    state: Dict[str, Dict[str, float]] = st.session_state.get(COST_RANGE_STATE_KEY, {})
    if not isinstance(state, dict):
        state = {}
    for _, row in updated.iterrows():
        code = str(row.get("コード", "")).strip()
        if not code:
            continue
        raw_min = row.get("最小 (％)", row.get("最小", 0.0) or 0.0)
        raw_typical = row.get("中央値 (％)", row.get("中央値", raw_min) or raw_min)
        raw_max = row.get("最大 (％)", row.get("最大", raw_typical) or raw_typical)
        try:
            minimum = float(raw_min)
        except (TypeError, ValueError):
            minimum = 0.0
        try:
            typical = float(raw_typical)
        except (TypeError, ValueError):
            typical = minimum
        try:
            maximum = float(raw_max)
        except (TypeError, ValueError):
            maximum = typical
        minimum = max(0.0, minimum)
        typical = max(minimum, typical)
        maximum = max(typical, maximum)
        if code in VARIABLE_RATIO_CODES:
            factor = 0.01
        else:
            factor = 1.0
        state[code] = {"min": minimum * factor, "typical": typical * factor, "max": maximum * factor}
    st.session_state[COST_RANGE_STATE_KEY] = state


def _calculate_sales_total(df: pd.DataFrame) -> Decimal:
    if df.empty:
        return Decimal("0")
    total = Decimal("0")
    for month_col in MONTH_COLUMNS:
        if month_col in df.columns:
            series = pd.to_numeric(df[month_col], errors="coerce").fillna(0.0)
            total += Decimal(str(series.sum()))
    return total


def _update_fermi_learning(plan_total: Decimal, actual_total: Decimal) -> None:
    learning_state: Dict[str, object] = st.session_state.get("fermi_learning", {})
    updated = update_learning_state(learning_state, plan_total, actual_total)
    st.session_state["fermi_learning"] = updated


def _ensure_nested_dict(target: Dict[str, object], template: Mapping[str, object]) -> None:
    for key, default_value in template.items():
        if isinstance(default_value, Mapping):
            current = target.get(key)
            if not isinstance(current, dict):
                target[key] = deepcopy(default_value)
            else:
                _ensure_nested_dict(current, default_value)
        else:
            if key not in target:
                target[key] = default_value


def _maybe_show_tutorial(step_id: str, message: str) -> None:
    if not st.session_state.get("tutorial_mode", True):
        return
    shown = st.session_state.get("tutorial_shown_steps")
    if not isinstance(shown, set):
        shown = set()
    if step_id in shown:
        return
    st.toast(message, icon="✦")
    shown.add(step_id)
    st.session_state["tutorial_shown_steps"] = shown


def _render_completion_checklist(flags: Dict[str, bool]) -> None:
    with st.expander("進捗チェックリスト", expanded=False):
        checklist_lines = []
        for step in WIZARD_STEPS:
            completed = flags.get(step["id"], False)
            icon = "✅" if completed else "⬜️"
            checklist_lines.append(
                f"<div class='wizard-checklist__item'><span>{icon}</span><span>{step['title']}</span></div>"
            )
        st.markdown("<div class='wizard-checklist'>" + "".join(checklist_lines) + "</div>", unsafe_allow_html=True)


def _calculate_completion_flags(
    *,
    context_state: Dict[str, str],
    sales_df: pd.DataFrame,
    variable_defaults: Dict[str, object],
    fixed_defaults: Dict[str, object],
    capex_df: pd.DataFrame,
    loan_df: pd.DataFrame,
) -> Dict[str, bool]:
    marketing_state = st.session_state.get(MARKETING_STRATEGY_KEY, {})
    context_complete = any(str(value).strip() for value in context_state.values()) or marketing_state_has_content(
        marketing_state
    )
    sales_complete = _calculate_sales_total(sales_df) > Decimal("0")
    variable_complete = any(Decimal(str(value)) > Decimal("0") for value in variable_defaults.values())
    fixed_complete = any(Decimal(str(value)) > Decimal("0") for value in fixed_defaults.values())
    invest_complete = False
    if not capex_df.empty:
        invest_complete = any(
            Decimal(str(row.get("金額", 0) if not pd.isna(row.get("金額", 0)) else 0)) > Decimal("0")
            for _, row in capex_df.iterrows()
        )
    if not invest_complete and not loan_df.empty:
        invest_complete = any(
            Decimal(str(row.get("元本", 0) if not pd.isna(row.get("元本", 0)) else 0)) > Decimal("0")
            for _, row in loan_df.iterrows()
        )
    tax_complete = bool(st.session_state.get("finance_models"))
    return {
        "context": context_complete,
        "sales": sales_complete,
        "costs": variable_complete or fixed_complete,
        "invest": invest_complete,
        "tax": tax_complete,
    }


def _apply_fermi_result(sales_df: pd.DataFrame) -> pd.DataFrame:
    result: Dict[str, object] | None = st.session_state.get(FERMI_RESULT_STATE_KEY)
    if not isinstance(result, dict):
        return sales_df
    monthly_adjusted = result.get("monthly_adjusted") or result.get("monthly_typical")
    if not monthly_adjusted:
        return sales_df
    values = list(monthly_adjusted)[: len(MONTH_SEQUENCE)]
    if len(values) < len(MONTH_SEQUENCE):
        values.extend([0.0] * (len(MONTH_SEQUENCE) - len(values)))

    new_df = sales_df.copy()
    channel = (str(result.get("channel", "")).strip() or f"チャネル{len(new_df) + 1}")
    product = (str(result.get("product", "")).strip() or "新規商品")
    customers = float(result.get("customers_typical", 0.0) or 0.0)
    unit_price_value = float(result.get("unit_price_typical", 0.0) or 0.0)
    memo = str(result.get("memo", "Fermi推定から自動入力")).strip()
    annual_min = float(result.get("annual_min", 0.0) or 0.0)
    annual_typical = float(result.get("annual_typical_adjusted", sum(values)) or sum(values))
    annual_max = float(result.get("annual_max", annual_typical) or annual_typical)

    target_index = result.get("target_index")
    if isinstance(target_index, int) and 0 <= target_index < len(new_df):
        row_idx = target_index
    else:
        row_idx = len(new_df)
        row_data = {col: 0.0 for col in MONTH_COLUMNS}
        row_data.update({
            "チャネル": channel,
            "商品": product,
            "想定顧客数": 0.0,
            "客単価": 0.0,
            "購入頻度(月)": 1.0,
            "メモ": memo,
            "年間売上(最低)": annual_min,
            "年間売上(中央値)": annual_typical,
            "年間売上(最高)": annual_max,
        })
        for idx, month in enumerate(MONTH_SEQUENCE):
            row_data[f"月{month:02d}"] = float(values[idx])
        new_df = pd.concat([new_df, pd.DataFrame([row_data])], ignore_index=True)
        row_idx = len(new_df) - 1

    new_df.at[row_idx, "チャネル"] = channel
    new_df.at[row_idx, "商品"] = product
    new_df.at[row_idx, "想定顧客数"] = customers
    new_df.at[row_idx, "客単価"] = unit_price_value
    new_df.at[row_idx, "購入頻度(月)"] = 1.0
    new_df.at[row_idx, "メモ"] = memo
    new_df.at[row_idx, "年間売上(最低)"] = annual_min
    new_df.at[row_idx, "年間売上(中央値)"] = annual_typical
    new_df.at[row_idx, "年間売上(最高)"] = annual_max

    for idx, month in enumerate(MONTH_SEQUENCE):
        new_df.at[row_idx, f"月{month:02d}"] = float(values[idx])

    st.session_state[FERMI_RESULT_STATE_KEY] = None
    return _standardize_sales_df(new_df)


def _render_fermi_wizard(sales_df: pd.DataFrame, unit: str) -> None:
    learning_state: Dict[str, object] = st.session_state.get("fermi_learning", {})
    avg_ratio = float(learning_state.get("avg_ratio", 1.0) or 1.0)
    history: List[Dict[str, object]] = learning_state.get("history", [])
    expand_default = st.session_state.get("tutorial_mode", False) and not history

    with st.expander("算 Fermi推定ウィザード", expanded=expand_default):
        st.markdown(
            "日次の来店数・客単価・営業日数を入力すると、年間売上の中央値/最低/最高レンジを推定します。"
            " 最小値・中央値・最大値で売上レンジを把握し、シナリオ比較に活用しましょう。"
            " 学習済みの実績データがあれば中央値を自動補正します。"
        )
        render_callout(
            icon="指",
            title="レンジ入力の目的",
            body="最小値は悲観ケース、中央値は標準ケース、最大値は成長ケースとして設定し、年間売上の幅やシナリオ分析に活用しましょう。推定結果はテンプレートの年間売上レンジにも反映できます。",
        )
        options_map = {
            f"{idx + 1}. {str(row.get('チャネル', ''))}/{str(row.get('商品', ''))}": idx
            for idx, row in sales_df.iterrows()
        }
        option_labels = list(options_map.keys())
        option_labels.append("新規行として追加")

        apply_learning = False
        with st.form("fermi_wizard_form"):
            selection = st.selectbox("適用先", option_labels, key="fermi_target_selection")
            target_index = options_map.get(selection)
            channel_default = (
                str(sales_df.loc[target_index, "チャネル"]) if target_index is not None else ""
            )
            product_default = (
                str(sales_df.loc[target_index, "商品"]) if target_index is not None else ""
            )
            channel_value = st.text_input(
                "チャネル名",
                value=channel_default,
                key="fermi_channel_input",
                help="推定結果を反映するチャネル名。新規行を追加する場合は入力してください。",
            )
            product_value = st.text_input(
                "商品・サービス名",
                value=product_default,
                key="fermi_product_input",
            )
            daily_min = st.number_input(
                "1日の平均来店数 (最小)",
                min_value=0.0,
                step=1.0,
                value=float(st.session_state.get("fermi_daily_min", 20.0)),
                key="fermi_daily_min",
            )
            daily_typical = st.number_input(
                "1日の平均来店数 (中央値)",
                min_value=0.0,
                step=1.0,
                value=float(st.session_state.get("fermi_daily_typical", 40.0)),
                key="fermi_daily_typical",
            )
            daily_max = st.number_input(
                "1日の平均来店数 (最大)",
                min_value=0.0,
                step=1.0,
                value=float(st.session_state.get("fermi_daily_max", 70.0)),
                key="fermi_daily_max",
            )
            price_min = st.number_input(
                "平均客単価 (最小)",
                min_value=0.0,
                step=100.0,
                value=float(st.session_state.get("fermi_price_min", 2000.0)),
                key="fermi_price_min",
            )
            price_typical = st.number_input(
                "平均客単価 (中央値)",
                min_value=0.0,
                step=100.0,
                value=float(st.session_state.get("fermi_price_typical", 3500.0)),
                key="fermi_price_typical",
            )
            price_max = st.number_input(
                "平均客単価 (最大)",
                min_value=0.0,
                step=100.0,
                value=float(st.session_state.get("fermi_price_max", 5000.0)),
                key="fermi_price_max",
            )
            days_min = st.number_input(
                "営業日数/月 (最小)",
                min_value=0,
                max_value=31,
                step=1,
                value=int(st.session_state.get("fermi_days_min", 20)),
                key="fermi_days_min",
            )
            days_typical = st.number_input(
                "営業日数/月 (中央値)",
                min_value=0,
                max_value=31,
                step=1,
                value=int(st.session_state.get("fermi_days_typical", 24)),
                key="fermi_days_typical",
            )
            days_max = st.number_input(
                "営業日数/月 (最大)",
                min_value=0,
                max_value=31,
                step=1,
                value=int(st.session_state.get("fermi_days_max", 28)),
                key="fermi_days_max",
            )
            seasonal_key = st.selectbox(
                "季節性パターン",
                list(FERMI_SEASONAL_PATTERNS.keys()),
                index=0,
                key="fermi_seasonal_key",
            )
            if history:
                default_learning = bool(st.session_state.get("fermi_apply_learning", True))
                apply_learning = st.toggle(
                    "過去実績から中央値を自動推定",
                    value=default_learning,
                    key="fermi_apply_learning",
                    help="保存済みの実績データと計画の比率を参照して中央値のみ自動補正します。",
                )
            else:
                st.caption("※ 過去実績を保存すると中央値を自動推定するスイッチが表示されます。")
                apply_learning = False
            submitted = st.form_submit_button("推定を計算", type="secondary")

        if submitted:
            daily_values = sorted([daily_min, daily_typical, daily_max])
            price_values = sorted([price_min, price_typical, price_max])
            day_values = sorted([float(days_min), float(days_typical), float(days_max)])
            estimate = compute_fermi_estimate(
                daily_visitors=(daily_values[0], daily_values[1], daily_values[2]),
                unit_price=(price_values[0], price_values[1], price_values[2]),
                business_days=(day_values[0], day_values[1], day_values[2]),
                seasonal_key=seasonal_key,
            )

            ratio = avg_ratio if apply_learning else 1.0
            adjusted_typical = estimate.typical_with_ratio(ratio)
            annual_adjusted = sum(adjusted_typical)

            metrics_cols = st.columns(3)
            with metrics_cols[0]:
                st.metric(
                    "中央値 (年間)",
                    format_amount_with_unit(Decimal(str(estimate.annual_typical)), "円"),
                )
            with metrics_cols[1]:
                st.metric(
                    "中央値 (補正後)",
                    format_amount_with_unit(Decimal(str(annual_adjusted)), "円"),
                    delta=f"x{ratio:.2f}",
                )
            with metrics_cols[2]:
                st.metric(
                    "レンジ幅",
                    format_amount_with_unit(
                        Decimal(str(estimate.annual_max - estimate.annual_min)), "円"
                    ),
                )

            preview_df = pd.DataFrame(
                {
                    "月": [f"{month}月" for month in MONTH_SEQUENCE],
                    "中央値": [float(value) for value in estimate.monthly],
                    "中央値(補正)": [float(value) for value in adjusted_typical],
                    "最低": [float(value) for value in estimate.monthly_min],
                    "最高": [float(value) for value in estimate.monthly_max],
                }
            )
            st.dataframe(
                preview_df,
                hide_index=True,
                use_container_width=True,
            )

            st.session_state[FERMI_RESULT_STATE_KEY] = {
                "target_index": target_index,
                "channel": channel_value,
                "product": product_value,
                "monthly_typical": [float(value) for value in estimate.monthly],
                "monthly_adjusted": [float(value) for value in adjusted_typical],
                "annual_min": float(estimate.annual_min),
                "annual_max": float(estimate.annual_max),
                "annual_typical": float(estimate.annual_typical),
                "annual_typical_adjusted": float(annual_adjusted),
                "customers_typical": float(daily_values[1] * day_values[1]),
                "unit_price_typical": float(price_values[1]),
                "memo": f"Fermi推定({seasonal_key})",
            }
            st.success("推定結果をプレビューしました。『推定結果をテンプレートに適用』を押すと反映されます。")

        if st.session_state.get(FERMI_RESULT_STATE_KEY):
            if st.button("推定結果をテンプレートに適用", type="primary", key="fermi_apply_button"):
                updated_df = _apply_fermi_result(sales_df)
                st.session_state[SALES_TEMPLATE_STATE_KEY] = updated_df
                st.toast("Fermi推定を売上テンプレートに反映しました。", icon="✔")
                st.experimental_rerun()

        if history:
            st.caption(f"過去{len(history)}件の実績学習に基づく中央値補正係数: x{avg_ratio:.2f}")
            history_rows: List[Dict[str, str]] = []
            for entry in reversed(history):
                plan_amount = Decimal(str(entry.get("plan", 0.0)))
                actual_amount = Decimal(str(entry.get("actual", 0.0)))
                diff_amount = Decimal(str(entry.get("diff", actual_amount - plan_amount)))
                history_rows.append(
                    {
                        "記録日時": str(entry.get("timestamp", ""))[:16],
                        "計画": format_amount_with_unit(plan_amount, "円"),
                        "実績": format_amount_with_unit(actual_amount, "円"),
                        "差異": format_amount_with_unit(diff_amount, "円"),
                        "比率": f"x{float(entry.get('ratio', 0.0)):.2f}",
                    }
                )
            history_df = pd.DataFrame(history_rows)
            st.dataframe(history_df, hide_index=True, use_container_width=True)


def _format_timestamp(value: object) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)

VARIABLE_RATIO_FIELDS = [
    (
        "COGS_MAT",
        "材料費率 (％)",
        "材料費＝製品・サービス提供に使う原材料コスト。粗利益率＝(売上−売上原価)÷売上。製造業では30%を超えると優良とされます。",
    ),
    (
        "COGS_LBR",
        "外部労務費率 (％)",
        "外部労務費＝外部人材への支払い。繁忙期の稼働計画を踏まえて設定しましょう。",
    ),
    (
        "COGS_OUT_SRC",
        "外注加工費率(専属) (％)",
        "専属パートナーに支払う加工コスト。受注量に応じた歩合を想定します。",
    ),
    (
        "COGS_OUT_CON",
        "外注加工費率(委託) (％)",
        "スポットで委託するコスト。最低発注量やキャンセル料も考慮してください。",
    ),
    (
        "COGS_OTH",
        "その他原価率 (％)",
        "その他の仕入や物流費など。粗利益率が目標レンジに収まるか確認しましょう。",
    ),
]

FIXED_COST_FIELDS = [
    (
        "OPEX_H",
        "人件費",
        "固定費",
        "正社員・パート・役員報酬などを合算。採用・昇給計画をメモに残すと振り返りやすくなります。",
    ),
    (
        "OPEX_DEP",
        "減価償却費",
        "固定費",
        "過去投資の償却費。税務上の耐用年数を確認しましょう。",
    ),
    (
        "OPEX_AD",
        "広告宣伝費",
        "販管費",
        "集客・販促のための広告費。キャンペーン計画と連動させて見直しましょう。",
    ),
    (
        "OPEX_UTIL",
        "水道光熱費",
        "販管費",
        "電気・ガス・水道などのエネルギーコスト。省エネ対策の効果測定に役立ちます。",
    ),
    (
        "OPEX_OTH",
        "その他販管費",
        "販管費",
        "通信費や備品費などその他の販管費。大きな支出はメモに残しておきましょう。",
    ),
]

FIXED_COST_CATEGORY = {code: category for code, _, category, _ in FIXED_COST_FIELDS}

LEGACY_OPEX_CODE = "OPEX_K"
LEGACY_OPEX_SPLIT = {
    "OPEX_AD": Decimal("0.4"),
    "OPEX_UTIL": Decimal("0.2"),
    "OPEX_OTH": Decimal("0.4"),
}


def _migrate_fixed_cost_payloads(
    fixed_costs: Dict[str, object], range_profiles: Dict[str, object]
) -> Tuple[Dict[str, object], Dict[str, object]]:
    migrated_costs = {str(key): value for key, value in fixed_costs.items()}
    migrated_ranges = {str(key): value for key, value in range_profiles.items()}

    if LEGACY_OPEX_CODE in migrated_costs and not any(
        code in migrated_costs for code in LEGACY_OPEX_SPLIT
    ):
        legacy_amount = Decimal(str(migrated_costs.pop(LEGACY_OPEX_CODE, 0.0)))
        for code, ratio in LEGACY_OPEX_SPLIT.items():
            if code not in migrated_costs:
                migrated_costs[code] = float(legacy_amount * ratio)

    if LEGACY_OPEX_CODE in migrated_ranges and not any(
        code in migrated_ranges for code in LEGACY_OPEX_SPLIT
    ):
        payload = migrated_ranges.pop(LEGACY_OPEX_CODE)
        if isinstance(payload, EstimateRange):
            base_profile = {
                "minimum": payload.minimum,
                "typical": payload.typical,
                "maximum": payload.maximum,
            }
        elif isinstance(payload, dict):
            base_profile = {
                "minimum": Decimal(str(payload.get("minimum", 0.0))),
                "typical": Decimal(str(payload.get("typical", 0.0))),
                "maximum": Decimal(str(payload.get("maximum", 0.0))),
            }
        else:
            base_profile = None
        if base_profile:
            for code, ratio in LEGACY_OPEX_SPLIT.items():
                migrated_ranges[code] = {
                    "minimum": float(base_profile["minimum"] * ratio),
                    "typical": float(base_profile["typical"] * ratio),
                    "maximum": float(base_profile["maximum"] * ratio),
                }

    return migrated_costs, migrated_ranges

NOI_FIELDS = [
    (
        "NOI_MISC",
        "雑収入",
        "本業以外の収益。補助金やポイント還元など小さな収益源もここに集約します。",
    ),
    (
        "NOI_GRANT",
        "補助金",
        "行政や財団からの補助金収入。採択時期と入金月を想定しておきましょう。",
    ),
    (
        "NOI_OTH",
        "その他営業外収益",
        "受取利息や資産売却益など。単発か継続かをメモしておくと精度が上がります。",
    ),
]

NOE_FIELDS = [
    (
        "NOE_INT",
        "支払利息",
        "借入に伴う金利コスト。借入スケジュールと連動しているか確認しましょう。",
    ),
    (
        "NOE_OTH",
        "その他費用",
        "雑損失や為替差損など一時的な費用。発生条件をメモすると再計算に便利です。",
    ),
]

VARIABLE_RATIO_CODES = {code for code, _, _ in VARIABLE_RATIO_FIELDS}
FIXED_COST_CODES = {code for code, _, _, _ in FIXED_COST_FIELDS}
NOI_CODES = {code for code, _, _ in NOI_FIELDS}
NOE_CODES = {code for code, _, _ in NOE_FIELDS}

CONSUMPTION_TAX_DEDUCTIBLE_CODES = {
    "COGS_MAT",
    "COGS_LBR",
    "COGS_OUT_SRC",
    "COGS_OUT_CON",
    "COGS_OTH",
    "OPEX_AD",
    "OPEX_UTIL",
    "OPEX_OTH",
    "NOE_OTH",
}

TAX_FIELD_META = {
    "corporate": "所得税・法人税率＝課税所得にかかる国税。おおむね30%前後が目安です。",
    "business": "事業税率＝経常利益に課される地方税。業種や規模により3〜5%程度が一般的です。",
    "consumption": "消費税率＝売上に上乗せする税率。免税事業者の場合は0%に設定します。",
    "dividend": "配当性向＝税引後利益に対する配当割合。成長投資を優先する場合は低めに設定。",
}


def _ensure_sales_template_state(base_df: pd.DataFrame) -> None:
    if SALES_TEMPLATE_STATE_KEY not in st.session_state:
        st.session_state[SALES_TEMPLATE_STATE_KEY] = base_df.copy()
        unique_channels = base_df["チャネル"].dropna().unique()
        unique_products = base_df["商品"].dropna().unique()
        st.session_state[SALES_CHANNEL_COUNTER_KEY] = len(unique_channels) + 1
        st.session_state[SALES_PRODUCT_COUNTER_KEY] = len(unique_products) + 1


def _template_preview_dataframe() -> pd.DataFrame:
    monthly_preview = {
        f"月{month:02d}": float(120000 + ((month - 1) % 3) * 20000)
        for month in MONTH_SEQUENCE
    }
    preview_row = {
        "チャネル": "オンライン",
        "商品": "主力商品A",
        "想定顧客数": 120,
        "客単価": 8000,
        "購入頻度(月)": 1.2,
        "年間売上(最低)": 1200000,
        "年間売上(中央値)": 1440000,
        "年間売上(最高)": 1680000,
        "メモ": "広告経由の継続顧客を想定",
        **monthly_preview,
    }
    ordered_columns = ["チャネル", "商品", *ASSUMPTION_COLUMNS, *MONTH_COLUMNS]
    return pd.DataFrame([preview_row], columns=ordered_columns)


def _format_row_label(index: int) -> str:
    return f"{index + 2}行目"


def _validate_sales_template(df: pd.DataFrame) -> List[str]:
    issues: List[str] = []
    if df is None:
        return ["ファイルの内容を読み取れませんでした。もう一度アップロードしてください。"]

    working = df.copy()
    working.columns = [str(col).strip() for col in working.columns]

    missing_columns = [col for col in REQUIRED_TEMPLATE_COLUMNS if col not in working.columns]
    if missing_columns:
        joined = "、".join(missing_columns)
        issues.append(
            f"必須列（{joined}）が見つかりません。ダウンロードしたテンプレートと同じ列構成にしてください。"
        )
        return issues

    if working.empty:
        issues.append("データ行がありません。1行以上のチャネル×商品行を入力してください。")
        return issues

    missing_tokens = {"", "nan", "none", "nat", "na", "<na>"}

    for column in REQUIRED_TEXT_TEMPLATE_COLUMNS:
        series = working[column]
        text_series = series.astype(str).str.strip()
        lower_series = text_series.str.lower()
        missing_mask = lower_series.isin(missing_tokens)
        for idx in working.index[missing_mask]:
            issues.append(f"{_format_row_label(idx)}『{column}』が未入力です。値を入力してください。")

    numeric_columns = [
        column
        for column in [*ASSUMPTION_NUMERIC_COLUMNS, *ASSUMPTION_RANGE_COLUMNS, *MONTH_COLUMNS]
        if column in working.columns
    ]

    for column in numeric_columns:
        series = working[column]
        text_series = series.astype(str).str.strip()
        lower_series = text_series.str.lower()
        missing_mask = lower_series.isin(missing_tokens)
        converted = pd.to_numeric(series, errors="coerce")
        invalid_mask = converted.isna() & ~missing_mask
        for idx in working.index[invalid_mask]:
            issues.append(
                f"{_format_row_label(idx)}『{column}』は数値で入力してください（現在の値: {text_series.iloc[idx]}）。"
            )
        if column in REQUIRED_NUMERIC_TEMPLATE_COLUMNS:
            for idx in working.index[missing_mask]:
                issues.append(f"{_format_row_label(idx)}『{column}』が未入力です。0以上の数値を入力してください。")

    return issues


def _standardize_sales_df(df: pd.DataFrame) -> pd.DataFrame:
    base = df.copy()
    base.columns = [str(col).strip() for col in base.columns]
    if "チャネル" not in base.columns or "商品" not in base.columns:
        raise ValueError("テンプレートには『チャネル』『商品』列が必要です。")
    for column in ASSUMPTION_NUMERIC_COLUMNS:
        if column not in base.columns:
            base[column] = 0.0
        base[column] = (
            pd.to_numeric(base[column], errors="coerce").fillna(0.0).astype(float)
        )
    for column in ASSUMPTION_RANGE_COLUMNS:
        if column not in base.columns:
            base[column] = 0.0
        base[column] = (
            pd.to_numeric(base[column], errors="coerce").fillna(0.0).astype(float)
        )
    for column in ASSUMPTION_TEXT_COLUMNS:
        if column not in base.columns:
            base[column] = ""
        base[column] = base[column].fillna("").astype(str)
    for month_col in MONTH_COLUMNS:
        if month_col not in base.columns:
            base[month_col] = 0.0
    ordered = ["チャネル", "商品", *ASSUMPTION_COLUMNS, *MONTH_COLUMNS]
    base = base[ordered]
    base["チャネル"] = base["チャネル"].fillna("").astype(str)
    base["商品"] = base["商品"].fillna("").astype(str)
    for month_col in MONTH_COLUMNS:
        base[month_col] = (
            pd.to_numeric(base[month_col], errors="coerce").fillna(0.0).astype(float)
        )
    return base


def _sales_template_to_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def _sales_template_to_excel(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="SalesTemplate", index=False)
    buffer.seek(0)
    return buffer.read()


def _load_sales_template_from_upload(upload: io.BytesIO | None) -> pd.DataFrame | None:
    if upload is None:
        return None
    file_size = getattr(upload, "size", None)
    if file_size is not None and file_size > MAX_UPLOAD_BYTES:
        st.error("アップロードできるファイルサイズは5MBまでです。")
        return None
    mime_type = getattr(upload, "type", "") or ""
    file_name = getattr(upload, "name", "")
    extension = Path(str(file_name)).suffix.lower()
    if mime_type and mime_type not in ALLOWED_MIME_TYPES:
        st.error("CSVまたはExcel形式のファイルをアップロードしてください。")
        return None
    if extension not in ALLOWED_EXTENSIONS:
        st.error("拡張子が .csv または .xlsx のファイルのみ受け付けます。")
        return None
    try:
        if extension == ".csv":
            df = pd.read_csv(upload)
        else:
            df = pd.read_excel(upload)
    except Exception:
        st.error("ファイルの読み込みに失敗しました。書式を確認してください。")
        return None
    issues = _validate_sales_template(df)
    if issues:
        for issue in issues:
            st.error(issue)
        return None
    try:
        return _standardize_sales_df(df)
    except ValueError as exc:
        st.error(str(exc))
    return None


def _yen_number_input(
    label: str,
    *,
    value: float,
    min_value: float = 0.0,
    max_value: float | None = None,
    step: float = 1.0,
    key: str | None = None,
    help: str | None = None,
) -> float:
    kwargs = {
        "min_value": float(min_value),
        "step": float(step),
        "value": float(value),
        "format": "%.0f",
    }
    if max_value is not None:
        kwargs["max_value"] = float(max_value)
    if key is not None:
        kwargs["key"] = key
    if help is not None:
        kwargs["help"] = help
    return float(st.number_input(label, **kwargs))


def _percent_number_input(
    label: str,
    *,
    value: float,
    min_value: float = 0.0,
    max_value: float | None = 1.0,
    step: float = 0.01,
    key: str | None = None,
    help: str | None = None,
) -> float:
    display_value = float(value) * 100.0
    display_min = float(min_value) * 100.0
    display_step = float(step) * 100.0 if step else 1.0
    kwargs = {
        "min_value": display_min,
        "step": display_step,
        "value": display_value,
        "format": "%.2f",
    }
    if max_value is not None:
        kwargs["max_value"] = float(max_value) * 100.0
    if key is not None:
        kwargs["key"] = key
    if help is not None:
        kwargs["help"] = help
    result = float(st.number_input(label, **kwargs))
    return result / 100.0


def _render_sales_guide_panel() -> None:
    st.markdown(
        """
        <div class="guide-panel" style="background-color:rgba(240,248,255,0.6);padding:1rem;border-radius:0.75rem;">
            <h4 style="margin-top:0;">✦ 入力ガイド</h4>
            <ul style="padding-left:1.2rem;">
                <li title="例示による入力イメージ">チャネル×商品×月の例：<strong>オンライン販売 10万円</strong>、<strong>店舗販売 5万円</strong>のように具体的な数字から積み上げると精度が高まります。</li>
                <li title="売上＝客数×客単価×購入頻度">売上は <strong>客数×客単価×購入頻度</strong> に分解すると改善ポイントが見えます。</li>
                <li title="チャネル別の獲得効率を把握">チャネルごとに行を分け、獲得効率や投資対効果を比較しましょう。</li>
                <li title="商品ライフサイクルに応じた山谷を設定">商品ごとに月別の山谷を設定し、販促や季節性を織り込みます。</li>
                <li title="テンプレートはCSV/Excelでオフライン編集可能">テンプレートはダウンロードしてオフラインで編集し、同じ形式でアップロードできます。</li>
            </ul>
            <div style="margin-top:1rem;padding:0.8rem 1rem;background-color:rgba(255,255,255,0.9);border:1px dashed #5f7da8;border-radius:0.75rem;line-height:1.6;">
                <strong style="display:block;margin-bottom:0.25rem;">オンラインチャネルの例</strong>
                <span style="display:block;">1日の平均来店数40人 × 平均客単価3,500円 × 月24日営業</span>
                <span style="display:block;margin-top:0.2rem;font-size:1.05rem;font-weight:600;">→ 年間売上336万円</span>
                <span style="display:block;margin-top:0.2rem;font-size:0.8rem;color:#1f3b5b;">※12か月営業で年間約4,032万円。数値を変えながらレンジを検討しましょう。</span>
            </div>
            <p style="margin-top:0.75rem;font-size:0.85rem;color:#1f3b5b;line-height:1.6;">
                最小値・中央値・最大値は、売上の下限〜上限レンジを把握し、悲観/標準/楽観シナリオを比較するための入力です。<br/>
                過去データがある場合はフェルミ推定ウィザードのスイッチで中央値を自動補正できます。
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

def _sales_dataframe(data: Dict) -> pd.DataFrame:
    rows: List[Dict[str, float | str]] = []
    for item in data.get("items", []):
        row: Dict[str, float | str] = {
            "チャネル": item.get("channel", ""),
            "商品": item.get("product", ""),
            "想定顧客数": float(Decimal(str(item.get("customers", 0) or 0))),
            "客単価": float(Decimal(str(item.get("unit_price", 0) or 0))),
            "購入頻度(月)": float(Decimal(str(item.get("purchase_frequency", 0) or 0))),
            "メモ": str(item.get("memo", "")),
        }
        monthly = item.get("monthly", {})
        amounts = monthly.get("amounts") if isinstance(monthly, dict) else None
        for idx, month in enumerate(MONTH_SEQUENCE, start=0):
            key = f"月{month:02d}"
            if isinstance(amounts, list):
                value = Decimal(str(amounts[idx])) if idx < len(amounts) else Decimal("0")
            elif isinstance(amounts, dict):
                value = Decimal(str(amounts.get(month, 0)))
            else:
                value = Decimal("0")
            row[key] = float(value)
        annual_total = sum((Decimal(str(row[f"月{m:02d}"])) for m in MONTH_SEQUENCE), start=Decimal("0"))
        revenue_range = item.get("revenue_range") if isinstance(item, dict) else None
        if isinstance(revenue_range, dict):
            try:
                range_obj = EstimateRange(**revenue_range)
            except Exception:
                range_obj = EstimateRange(minimum=annual_total, typical=annual_total, maximum=annual_total)
        elif isinstance(revenue_range, EstimateRange):
            range_obj = revenue_range
        else:
            range_obj = EstimateRange(minimum=annual_total, typical=annual_total, maximum=annual_total)
        row["年間売上(最低)"] = float(range_obj.minimum)
        row["年間売上(中央値)"] = float(range_obj.typical)
        row["年間売上(最高)"] = float(range_obj.maximum)
        rows.append(row)
    if not rows:
        rows.append(
            {
                "チャネル": "オンライン",
                "商品": "主力製品",
                "想定顧客数": 0.0,
                "客単価": 0.0,
                "購入頻度(月)": 1.0,
                "メモ": "",
                "年間売上(最低)": 0.0,
                "年間売上(中央値)": 0.0,
                "年間売上(最高)": 0.0,
                **{f"月{m:02d}": 0.0 for m in MONTH_SEQUENCE},
            }
        )
    df = pd.DataFrame(rows)
    return df


def _industry_sales_dataframe(template_key: str) -> pd.DataFrame:
    template = INDUSTRY_TEMPLATES.get(template_key)
    if template is None:
        return pd.DataFrame(
            [
                {
                    "チャネル": "オンライン",
                    "商品": "主力製品",
                    "想定顧客数": 0.0,
                    "客単価": 0.0,
                    "購入頻度(月)": 1.0,
                    "メモ": "",
                    **{f"月{m:02d}": 0.0 for m in MONTH_SEQUENCE},
                }
            ]
        )
    rows: List[Dict[str, float | str]] = []
    for sales_row in template.sales_rows:
        pattern = sales_row.normalized_pattern()
        base_monthly = sales_row.customers * sales_row.unit_price * sales_row.frequency
        monthly_amounts = [float(base_monthly * weight) for weight in pattern]
        row: Dict[str, float | str] = {
            "チャネル": sales_row.channel,
            "商品": sales_row.product,
            "想定顧客数": float(sales_row.customers),
            "客単価": float(sales_row.unit_price),
            "購入頻度(月)": float(sales_row.frequency),
            "メモ": sales_row.memo,
        }
        for idx, month in enumerate(MONTH_SEQUENCE):
            row[f"月{month:02d}"] = monthly_amounts[idx]
        annual_total = float(sum(monthly_amounts))
        row["年間売上(最低)"] = annual_total
        row["年間売上(中央値)"] = annual_total
        row["年間売上(最高)"] = annual_total
        rows.append(row)
    return pd.DataFrame(rows)


def _apply_industry_template(template_key: str, unit_factor: Decimal) -> None:
    template = INDUSTRY_TEMPLATES.get(template_key)
    if template is None:
        st.error("選択した業種テンプレートが見つかりません。")
        return

    df = _standardize_sales_df(_industry_sales_dataframe(template_key))
    st.session_state[SALES_TEMPLATE_STATE_KEY] = df
    st.session_state[SALES_CHANNEL_COUNTER_KEY] = len(df["チャネル"].unique()) + 1
    st.session_state[SALES_PRODUCT_COUNTER_KEY] = len(df) + 1
    st.session_state[INDUSTRY_TEMPLATE_KEY] = template_key

    for code, ratio in template.variable_ratios.items():
        st.session_state[f"var_ratio_{code}"] = float(ratio)
    for code, amount in template.fixed_costs.items():
        st.session_state[f"fixed_cost_{code}"] = float(
            Decimal(str(amount)) / (unit_factor or Decimal("1"))
        )
    for code, amount in template.non_operating_income.items():
        st.session_state[f"noi_{code}"] = float(
            Decimal(str(amount)) / (unit_factor or Decimal("1"))
        )
    for code, amount in template.non_operating_expenses.items():
        st.session_state[f"noe_{code}"] = float(
            Decimal(str(amount)) / (unit_factor or Decimal("1"))
        )

    st.session_state["working_capital_profile"] = template.working_capital.copy()
    metric_state: Dict[str, Dict[str, float]] = st.session_state.get(
        "industry_custom_metrics", {}
    )
    metric_state[template_key] = template.custom_metrics
    st.session_state["industry_custom_metrics"] = metric_state
    st.toast(f"{template.label}のテンプレートを適用しました。", icon="□")


def _capex_dataframe(data: Dict) -> pd.DataFrame:
    items = data.get("items", [])
    if not items:
        return pd.DataFrame(
            [{"投資名": "新工場設備", "金額": 0.0, "開始月": 1, "耐用年数": 5}]
        )
    rows = []
    for item in items:
        rows.append(
            {
                "投資名": item.get("name", ""),
                "金額": float(Decimal(str(item.get("amount", 0)))),
                "開始月": int(item.get("start_month", 1)),
                "耐用年数": int(item.get("useful_life_years", 5)),
            }
        )
    return pd.DataFrame(rows)


def _loan_dataframe(data: Dict) -> pd.DataFrame:
    loans = data.get("loans", [])
    if not loans:
        return pd.DataFrame(
            [
                {
                    "名称": "メインバンク借入",
                    "元本": 0.0,
                    "金利": 0.01,
                    "返済期間(月)": 60,
                    "開始月": 1,
                    "返済タイプ": "equal_principal",
                }
            ]
        )
    rows = []
    for loan in loans:
        rows.append(
            {
                "名称": loan.get("name", ""),
                "元本": float(Decimal(str(loan.get("principal", 0)))),
                "金利": float(Decimal(str(loan.get("interest_rate", 0)))),
                "返済期間(月)": int(loan.get("term_months", 12)),
                "開始月": int(loan.get("start_month", 1)),
                "返済タイプ": loan.get("repayment_type", "equal_principal"),
            }
        )
    return pd.DataFrame(rows)


def _serialize_capex_editor_df(df: pd.DataFrame) -> Dict[str, object]:
    items: List[Dict[str, object]] = []
    for _, row in df.iterrows():
        raw_amount = row.get("金額", 0)
        try:
            amount = Decimal(str(0 if pd.isna(raw_amount) else raw_amount))
        except Exception:
            continue
        if amount <= 0:
            continue
        name = ("" if pd.isna(row.get("投資名", "")) else str(row.get("投資名", ""))).strip() or "未設定"
        raw_start = row.get("開始月", 1)
        start_month = int(raw_start if not pd.isna(raw_start) else 1)
        raw_life = row.get("耐用年数", 5)
        useful_life = int(raw_life if not pd.isna(raw_life) else 5)
        items.append(
            {
                "name": name,
                "amount": amount,
                "start_month": max(1, min(12, start_month)),
                "useful_life_years": max(1, useful_life),
            }
        )
    return {"items": items}


def _serialize_loan_editor_df(df: pd.DataFrame) -> Dict[str, object]:
    loans: List[Dict[str, object]] = []
    for _, row in df.iterrows():
        raw_principal = row.get("元本", 0)
        try:
            principal = Decimal(str(0 if pd.isna(raw_principal) else raw_principal))
        except Exception:
            continue
        if principal <= 0:
            continue
        raw_rate = row.get("金利", 0)
        try:
            interest_rate = Decimal(str(0 if pd.isna(raw_rate) else raw_rate))
        except Exception:
            interest_rate = Decimal("0")
        raw_term = row.get("返済期間(月)", 12)
        term_months = int(raw_term if not pd.isna(raw_term) else 12)
        raw_start = row.get("開始月", 1)
        start_month = int(raw_start if not pd.isna(raw_start) else 1)
        repayment_type = row.get("返済タイプ", "equal_principal")
        repayment_value = (
            str(repayment_type)
            if str(repayment_type) in {"equal_principal", "interest_only"}
            else "equal_principal"
        )
        loans.append(
            {
                "name": ("" if pd.isna(row.get("名称", "")) else str(row.get("名称", ""))).strip() or "借入",
                "principal": principal,
                "interest_rate": interest_rate,
                "term_months": max(1, term_months),
                "start_month": max(1, min(12, start_month)),
                "repayment_type": repayment_value,
            }
        )
    return {"loans": loans}


def _build_bundle_payload_from_inputs(
    sales_df: pd.DataFrame,
    variable_inputs: Dict[str, float],
    fixed_inputs: Dict[str, float],
    noi_inputs: Dict[str, float],
    noe_inputs: Dict[str, float],
    *,
    unit_factor: Decimal,
    cost_range_state: Dict[str, Dict[str, float]],
    capex_df: pd.DataFrame,
    loan_df: pd.DataFrame,
    tax_payload: Dict[str, Decimal],
) -> Dict[str, object]:
    sales_data = {"items": []}
    for _, row in sales_df.fillna(0).iterrows():
        monthly_amounts = [Decimal(str(row.get(month, 0))) for month in MONTH_COLUMNS]
        customers_val = Decimal(str(row.get("想定顧客数", 0)))
        unit_price_val = Decimal(str(row.get("客単価", 0)))
        frequency_val = Decimal(str(row.get("購入頻度(月)", 0)))
        memo_val = str(row.get("メモ", "")).strip()
        annual_min_val = Decimal(str(row.get("年間売上(最低)", 0)))
        annual_typical_val = Decimal(str(row.get("年間売上(中央値)", 0)))
        annual_max_val = Decimal(str(row.get("年間売上(最高)", 0)))
        sales_data["items"].append(
            {
                "channel": str(row.get("チャネル", "")).strip() or "未設定",
                "product": str(row.get("商品", "")).strip() or "未設定",
                "monthly": {"amounts": monthly_amounts},
                "customers": customers_val if customers_val > 0 else None,
                "unit_price": unit_price_val if unit_price_val > 0 else None,
                "purchase_frequency": frequency_val if frequency_val > 0 else None,
                "memo": memo_val or None,
                "revenue_range": {
                    "minimum": annual_min_val,
                    "typical": annual_typical_val if annual_typical_val > 0 else sum(monthly_amounts),
                    "maximum": max(annual_max_val, annual_typical_val, sum(monthly_amounts)),
                },
            }
        )

    range_profiles: Dict[str, Dict[str, Decimal]] = {}
    for code, profile in (cost_range_state or {}).items():
        min_val = Decimal(str(profile.get("min", 0.0)))
        typ_val = Decimal(str(profile.get("typical", 0.0)))
        max_val = Decimal(str(profile.get("max", 0.0)))
        if code in VARIABLE_RATIO_CODES:
            divisor = Decimal("1")
        else:
            divisor = unit_factor or Decimal("1")
            min_val *= divisor
            typ_val *= divisor
            max_val *= divisor
        ordered = sorted([min_val, typ_val, max_val])
        if any(value > Decimal("0") for value in ordered):
            range_profiles[code] = {
                "minimum": ordered[0],
                "typical": ordered[1],
                "maximum": ordered[2],
            }

    multiplier = unit_factor or Decimal("1")
    costs_data = {
        "variable_ratios": {code: Decimal(str(value)) for code, value in variable_inputs.items()},
        "fixed_costs": {code: Decimal(str(value)) * multiplier for code, value in fixed_inputs.items()},
        "non_operating_income": {
            code: Decimal(str(value)) * multiplier for code, value in noi_inputs.items()
        },
        "non_operating_expenses": {
            code: Decimal(str(value)) * multiplier for code, value in noe_inputs.items()
        },
    }
    if range_profiles:
        costs_data["range_profiles"] = range_profiles

    capex_data = _serialize_capex_editor_df(capex_df)
    loan_data = _serialize_loan_editor_df(loan_df)

    return {
        "sales": sales_data,
        "costs": costs_data,
        "capex": capex_data,
        "loans": loan_data,
        "tax": tax_payload,
    }


sales_defaults_df = _sales_dataframe(finance_raw.get("sales", {}))
_ensure_sales_template_state(sales_defaults_df)
stored_sales_df = st.session_state.get(SALES_TEMPLATE_STATE_KEY, sales_defaults_df)
try:
    sales_df = _standardize_sales_df(pd.DataFrame(stored_sales_df))
except ValueError:
    sales_df = sales_defaults_df.copy()
st.session_state[SALES_TEMPLATE_STATE_KEY] = sales_df

capex_defaults_df = _capex_dataframe(finance_raw.get("capex", {}))
loan_defaults_df = _loan_dataframe(finance_raw.get("loans", {}))

costs_defaults = finance_raw.get("costs", {})
fixed_costs_raw = dict(costs_defaults.get("fixed_costs", {}))
range_defaults_raw = dict(costs_defaults.get("range_profiles", {}))
fixed_costs, migrated_ranges = _migrate_fixed_cost_payloads(fixed_costs_raw, range_defaults_raw)
costs_defaults["fixed_costs"] = fixed_costs
costs_defaults["range_profiles"] = migrated_ranges
finance_raw.setdefault("costs", costs_defaults)

variable_ratios = costs_defaults.get("variable_ratios", {})
noi_defaults = costs_defaults.get("non_operating_income", {})
noe_defaults = costs_defaults.get("non_operating_expenses", {})

tax_defaults = finance_raw.get("tax", {})

settings_state: Dict[str, object] = st.session_state.get("finance_settings", {})
unit = str(settings_state.get("unit", "百万円"))
unit_factor = UNIT_FACTORS.get(unit, Decimal("1"))

_ensure_cost_range_state(
    costs_defaults.get("range_profiles", {}),
    variable_defaults=variable_ratios,
    fixed_defaults=fixed_costs,
    noi_defaults=noi_defaults,
    noe_defaults=noe_defaults,
    unit_factor=unit_factor,
)


def _set_wizard_step(step_id: str) -> None:
    st.session_state[INPUT_WIZARD_STEP_KEY] = step_id


def _get_step_index(step_id: str) -> int:
    for idx, step in enumerate(WIZARD_STEPS):
        if step["id"] == step_id:
            return idx
    return 0


def _render_stepper(current_step: str) -> int:
    step_index = _get_step_index(current_step)
    progress_ratio = (step_index + 1) / len(WIZARD_STEPS)
    st.progress(progress_ratio, text=f"ステップ {step_index + 1} / {len(WIZARD_STEPS)}")
    labels: List[str] = []
    for idx, step in enumerate(WIZARD_STEPS):
        label = f"{idx + 1}. {step['title']}"
        if step["id"] == current_step:
            label = f"**{label}**"
        labels.append(label)
    st.markdown(" → ".join(labels))
    st.caption(WIZARD_STEPS[step_index]["description"])
    return step_index


def _render_navigation(step_index: int) -> None:
    prev_step_id = WIZARD_STEPS[step_index - 1]["id"] if step_index > 0 else None
    next_step_id = WIZARD_STEPS[step_index + 1]["id"] if step_index < len(WIZARD_STEPS) - 1 else None
    nav_cols = st.columns([1, 1, 6])
    with nav_cols[0]:
        if prev_step_id is not None:
            st.button(
                "← 戻る",
                **use_container_width_kwargs(st.button),
                on_click=_set_wizard_step,
                args=(prev_step_id,),
                key=f"prev_{step_index}",
            )
        else:
            st.markdown("&nbsp;")
    with nav_cols[1]:
        if next_step_id is not None:
            st.button(
                "次へ →",
                **use_container_width_kwargs(st.button),
                type="primary",
                on_click=_set_wizard_step,
                args=(next_step_id,),
                key=f"next_{step_index}",
            )
        else:
            st.markdown("&nbsp;")
    with nav_cols[2]:
        if next_step_id is not None:
            st.caption(f"次のステップ：{WIZARD_STEPS[step_index + 1]['title']}")
        else:
            st.caption("ウィザードの最後です。内容を保存しましょう。")


def _variable_inputs_from_state(defaults: Dict[str, object]) -> Dict[str, float]:
    values: Dict[str, float] = {}
    for code, _, _ in VARIABLE_RATIO_FIELDS:
        key = f"var_ratio_{code}"
        default_ratio = float(defaults.get(code, 0.0))
        stored_value = st.session_state.get(key, default_ratio * 100.0)
        try:
            ratio = float(stored_value) / 100.0
        except (TypeError, ValueError):
            ratio = default_ratio
        values[code] = max(0.0, min(1.0, ratio))
    return values


def _monetary_inputs_from_state(
    defaults: Dict[str, object],
    fields,
    prefix: str,
    unit_factor: Decimal,
) -> Dict[str, float]:
    values: Dict[str, float] = {}
    for field in fields:
        code = field[0]
        key = f"{prefix}_{code}"
        default_value = float(Decimal(str(defaults.get(code, 0.0))) / unit_factor)
        values[code] = float(st.session_state.get(key, default_value))
    return values


if INPUT_WIZARD_STEP_KEY not in st.session_state:
    st.session_state[INPUT_WIZARD_STEP_KEY] = WIZARD_STEPS[0]["id"]

if BUSINESS_CONTEXT_KEY not in st.session_state:
    st.session_state[BUSINESS_CONTEXT_KEY] = BUSINESS_CONTEXT_TEMPLATE.copy()
context_state: Dict[str, str] = st.session_state[BUSINESS_CONTEXT_KEY]

if (
    MARKETING_STRATEGY_KEY not in st.session_state
    or not isinstance(st.session_state[MARKETING_STRATEGY_KEY], dict)
):
    st.session_state[MARKETING_STRATEGY_KEY] = empty_marketing_state()
else:
    _ensure_nested_dict(
        st.session_state[MARKETING_STRATEGY_KEY],
        empty_marketing_state(),
    )
marketing_state: Dict[str, object] = st.session_state[MARKETING_STRATEGY_KEY]

if (
    STRATEGIC_ANALYSIS_KEY not in st.session_state
    or not isinstance(st.session_state[STRATEGIC_ANALYSIS_KEY], dict)
):
    st.session_state[STRATEGIC_ANALYSIS_KEY] = {"swot": [], "pest": []}
strategic_state: Dict[str, object] = st.session_state[STRATEGIC_ANALYSIS_KEY]
if "swot" not in strategic_state:
    strategic_state["swot"] = []
if "pest" not in strategic_state:
    strategic_state["pest"] = []
if "swot_editor_df" not in st.session_state:
    st.session_state["swot_editor_df"] = _swot_editor_dataframe_from_state(
        strategic_state.get("swot") if isinstance(strategic_state.get("swot"), list) else []
    )
if "pest_editor_df" not in st.session_state:
    st.session_state["pest_editor_df"] = _pest_editor_dataframe_from_state(
        strategic_state.get("pest") if isinstance(strategic_state.get("pest"), list) else []
    )

if BUSINESS_CONTEXT_SNAPSHOT_KEY not in st.session_state:
    st.session_state[BUSINESS_CONTEXT_SNAPSHOT_KEY] = {
        key: str(context_state.get(key, "")) for key in BUSINESS_CONTEXT_TEMPLATE
    }
if BUSINESS_CONTEXT_LAST_SAVED_KEY not in st.session_state:
    st.session_state[BUSINESS_CONTEXT_LAST_SAVED_KEY] = (
        datetime.now().replace(microsecond=0).isoformat()
    )
if MARKETING_STRATEGY_SNAPSHOT_KEY not in st.session_state:
    st.session_state[MARKETING_STRATEGY_SNAPSHOT_KEY] = json.dumps(
        marketing_state,
        ensure_ascii=False,
        sort_keys=True,
    )

if "capex_editor_df" not in st.session_state:
    st.session_state["capex_editor_df"] = capex_defaults_df.copy()
if "loan_editor_df" not in st.session_state:
    st.session_state["loan_editor_df"] = loan_defaults_df.copy()

for code, _, _ in VARIABLE_RATIO_FIELDS:
    default_ratio = float(variable_ratios.get(code, 0.0))
    st.session_state.setdefault(f"var_ratio_{code}", default_ratio * 100.0)
for code, _, _, _ in FIXED_COST_FIELDS:
    default_value = float(Decimal(str(fixed_costs.get(code, 0.0))) / unit_factor)
    st.session_state.setdefault(f"fixed_cost_{code}", default_value)
for code, _, _ in NOI_FIELDS:
    default_value = float(Decimal(str(noi_defaults.get(code, 0.0))) / unit_factor)
    st.session_state.setdefault(f"noi_{code}", default_value)
for code, _, _ in NOE_FIELDS:
    default_value = float(Decimal(str(noe_defaults.get(code, 0.0))) / unit_factor)
    st.session_state.setdefault(f"noe_{code}", default_value)

st.session_state.setdefault("tax_corporate_rate", float(tax_defaults.get("corporate_tax_rate", 0.3)))
st.session_state.setdefault("tax_business_rate", float(tax_defaults.get("business_tax_rate", 0.05)))
st.session_state.setdefault("tax_consumption_rate", float(tax_defaults.get("consumption_tax_rate", 0.1)))
st.session_state.setdefault("tax_dividend_ratio", float(tax_defaults.get("dividend_payout_ratio", 0.0)))

current_step = str(st.session_state[INPUT_WIZARD_STEP_KEY])

capex_editor_snapshot = pd.DataFrame(st.session_state.get("capex_editor_df", capex_defaults_df))
loan_editor_snapshot = pd.DataFrame(st.session_state.get("loan_editor_df", loan_defaults_df))

completion_flags = _calculate_completion_flags(
    context_state=context_state,
    sales_df=sales_df,
    variable_defaults=variable_ratios,
    fixed_defaults=fixed_costs,
    capex_df=capex_editor_snapshot,
    loan_df=loan_editor_snapshot,
)

st.title("データ入力ハブ")
st.caption("ウィザード形式で売上から投資までを順番に整理します。保存すると全ページに反映されます。")

st.sidebar.title("ヘルプセンター")
with st.sidebar.expander("よくある質問 (FAQ)", expanded=False):
    st.markdown(
        """
        **Q. 売上計画はどの程度細かく分類すべきですか？**  \\
        A. 改善アクションを検討できる単位（チャネル×商品など）での分解を推奨します。\\
        \\
        **Q. 数値がまだ固まっていない場合は？**  \\
        A. 過去実績や他社事例から仮置きし、コメント欄に前提条件をメモすると更新が楽になります。\\
        \\
        **Q. 入力途中で別ステップに移動しても大丈夫？**  \\
        A. 各ステップは自動保存されます。最終的に「保存」を押すと財務計画に反映されます。
        """
    )
with st.sidebar.expander("用語集", expanded=False):
    st.markdown(
        """
        - **粗利益率**： (売上 − 売上原価) ÷ 売上。製造業では30%超が目安。\\
        - **変動費**： 売上に比例して増減する費用。材料費や外注費など。\\
        - **固定費**： 毎月一定で発生する費用。人件費や家賃など。\\
        - **CAPEX**： 設備投資。長期にわたり利用する資産の購入費用。\\
        - **借入金**： 金融機関等からの調達。金利と返済期間を設定します。
        """
    )
st.sidebar.info("入力途中でもステップを行き来できます。最終ステップで保存すると数値が確定します。")

step_index = _render_stepper(current_step)
_render_completion_checklist(completion_flags)

if current_step == "context":
    _maybe_show_tutorial("context", "顧客・自社・競合の視点を整理して仮説の前提を固めましょう。")
    st.header("STEP 1｜ビジネスモデル整理")
    st.markdown("3C分析とビジネスモデルキャンバスの主要要素を整理して、数値入力の前提を明確にしましょう。")
    st.info("顧客(Customer)・自社(Company)・競合(Competitor)の視点を1〜2行でも言語化することで、収益モデルの仮定がぶれにくくなります。")

    last_saved_iso = st.session_state.get(BUSINESS_CONTEXT_LAST_SAVED_KEY)
    if last_saved_iso:
        try:
            saved_dt = datetime.fromisoformat(str(last_saved_iso))
            saved_label = saved_dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            saved_label = str(last_saved_iso)
        st.caption(f"保存ステータス: 入力内容は自動保存されます（最終保存: {saved_label}）")
    else:
        st.caption("保存ステータス: 入力内容は自動保存されます。")

    three_c_cols = st.columns(3)
    with three_c_cols[0]:
        context_state["three_c_customer"] = st.text_area(
            "Customer（顧客）",
            value=context_state.get("three_c_customer", ""),
            placeholder=BUSINESS_CONTEXT_PLACEHOLDER["three_c_customer"],
            help="想定顧客層や顧客課題を記入してください。",
            height=150,
        )
        st.caption(CUSTOMER_EXAMPLE_TEXT)
    with three_c_cols[1]:
        context_state["three_c_company"] = st.text_area(
            "Company（自社）",
            value=context_state.get("three_c_company", ""),
            placeholder=BUSINESS_CONTEXT_PLACEHOLDER["three_c_company"],
            help="自社の強み・提供価値・リソースを整理しましょう。",
            height=150,
        )
    with three_c_cols[2]:
        context_state["three_c_competitor"] = st.text_area(
            "Competitor（競合）",
            value=context_state.get("three_c_competitor", ""),
            placeholder=BUSINESS_CONTEXT_PLACEHOLDER["three_c_competitor"],
            help="競合の特徴や比較したときの優位性・弱点を記入します。",
            height=150,
        )

    st.markdown("#### ビジネスモデルキャンバス（主要要素）")
    bmc_cols = st.columns(3)
    with bmc_cols[0]:
        context_state["bmc_customer_segments"] = st.text_area(
            "顧客セグメント",
            value=context_state.get("bmc_customer_segments", ""),
            placeholder=BUSINESS_CONTEXT_PLACEHOLDER["bmc_customer_segments"],
            help="年齢・職種・企業規模など、ターゲット顧客の解像度を高めましょう。",
            height=160,
        )
    with bmc_cols[1]:
        context_state["bmc_value_proposition"] = st.text_area(
            "提供価値",
            value=context_state.get("bmc_value_proposition", ""),
            placeholder=BUSINESS_CONTEXT_PLACEHOLDER["bmc_value_proposition"],
            help="顧客課題をどのように解決するか、成功事例なども記載すると有効です。",
            height=160,
        )
    with bmc_cols[2]:
        context_state["bmc_channels"] = st.text_area(
            "チャネル",
            value=context_state.get("bmc_channels", ""),
            placeholder=BUSINESS_CONTEXT_PLACEHOLDER["bmc_channels"],
            help="オンライン・オフラインの接点や販売フローを整理してください。",
            height=160,
        )

    context_state["qualitative_memo"] = st.text_area(
        "事業計画メモ",
        value=context_state.get("qualitative_memo", ""),
        placeholder=BUSINESS_CONTEXT_PLACEHOLDER["qualitative_memo"],
        help="KGI/KPIの設定根拠、注意点、投資判断に必要な情報などを自由に記入できます。",
        height=140,
    )
    st.caption("※ 記入した内容はウィザード内で保持され、事業計画書作成時の定性情報として活用できます。")

    st.markdown("#### マーケティング戦略（4P/3C入力）")
    st.caption(
        "製品（Product）・価格（Price）・流通チャネル（Place）・プロモーション（Promotion）の4Pは、"
        "マーケティングミックスの基本構成要素であり、効果的な市場戦略を組み立てる土台となります（Investopedia）。"
    )
    st.markdown("##### 4Pの現状整理と課題")
    st.caption("現状・課題・重視するKPIを記入すると、下部で強化策が自動提案されます。")

    four_p_state = marketing_state.get("four_p", {})
    for key in FOUR_P_KEYS:
        label = FOUR_P_LABELS[key]
        entry = four_p_state.get(key, {})
        guide = FOUR_P_INPUT_GUIDE.get(key, {})
        with st.expander(label, expanded=(key == "product")):
            entry["current"] = st.text_area(
                f"{label}｜現状の取り組み",
                value=str(entry.get("current", "")),
                placeholder=str(guide.get("current", "")),
                height=130,
            )
            entry["challenge"] = st.text_area(
                f"{label}｜課題・制約",
                value=str(entry.get("challenge", "")),
                placeholder=str(guide.get("challenge", "")),
                height=120,
            )
            entry["metric"] = st.text_input(
                f"{label}｜重視するKPI・数値目標",
                value=str(entry.get("metric", "")),
                placeholder=str(guide.get("metric", "")),
                help="具体的な数値（例：解約率5%、月間リード120件など）を入れると提案が精緻になります。",
            )
            if key == "price":
                try:
                    current_price = float(entry.get("price_point", 0.0) or 0.0)
                except (TypeError, ValueError):
                    current_price = 0.0
                entry["price_point"] = st.number_input(
                    "自社の主要プラン価格（円・税込/税抜いずれでも可）",
                    min_value=0.0,
                    value=current_price,
                    step=100.0,
                    help="平均的な契約金額や代表的なプラン価格を入力してください。",
                )

    st.markdown("##### Customer（市場・顧客）")
    customer_state = marketing_state.get("customer", {})
    customer_cols = st.columns(2)
    with customer_cols[0]:
        try:
            market_size_value = float(customer_state.get("market_size", 0.0) or 0.0)
        except (TypeError, ValueError):
            market_size_value = 0.0
        customer_state["market_size"] = st.number_input(
            "市場規模（円や想定ユーザー数）",
            min_value=0.0,
            value=market_size_value,
            step=1000.0,
            help="単位は自由です。例：1200000000（円）や2000（社）。",
        )
        try:
            growth_value = float(customer_state.get("growth_rate", 0.0) or 0.0)
        except (TypeError, ValueError):
            growth_value = 0.0
        customer_state["growth_rate"] = st.number_input(
            "年成長率（%）",
            min_value=-100.0,
            max_value=500.0,
            value=growth_value,
            step=1.0,
        )
    with customer_cols[1]:
        customer_state["needs"] = st.text_area(
            "主要ニーズ・顧客課題",
            value=str(customer_state.get("needs", "")),
            placeholder=MARKETING_CUSTOMER_PLACEHOLDER["needs"],
            height=120,
        )
        customer_state["segments"] = st.text_area(
            "顧客セグメント",
            value=str(customer_state.get("segments", "")),
            placeholder=MARKETING_CUSTOMER_PLACEHOLDER["segments"],
            height=120,
        )
    customer_state["persona"] = st.text_area(
        "ターゲット顧客ペルソナ",
        value=str(customer_state.get("persona", "")),
        placeholder=MARKETING_CUSTOMER_PLACEHOLDER["persona"],
        height=110,
    )

    st.markdown("##### Company（自社の整理）")
    company_state = marketing_state.get("company", {})
    company_cols = st.columns(2)
    with company_cols[0]:
        company_state["strengths"] = st.text_area(
            "自社の強み",
            value=str(company_state.get("strengths", "")),
            placeholder=MARKETING_COMPANY_PLACEHOLDER["strengths"],
            height=120,
        )
        company_state["resources"] = st.text_area(
            "差別化リソース・提供体制",
            value=str(company_state.get("resources", "")),
            placeholder=MARKETING_COMPANY_PLACEHOLDER["resources"],
            height=120,
        )
    with company_cols[1]:
        company_state["weaknesses"] = st.text_area(
            "弱み・制約",
            value=str(company_state.get("weaknesses", "")),
            placeholder=MARKETING_COMPANY_PLACEHOLDER["weaknesses"],
            height=120,
        )
        try:
            service_score_value = float(company_state.get("service_score", 3.0) or 3.0)
        except (TypeError, ValueError):
            service_score_value = 3.0
        company_state["service_score"] = st.number_input(
            "自社サービス差別化スコア (1-5)",
            min_value=1.0,
            max_value=5.0,
            value=service_score_value,
            step=0.1,
            help="顧客体験・サポート品質などを1（低い）〜5（高い）で主観評価します。",
        )

    st.markdown("##### Competitor（競合比較）")
    st.caption(MARKETING_COMPETITOR_HELP)
    competitor_state = marketing_state.get("competitor", {})
    competitor_cols = st.columns(2)
    top_state = competitor_state.get("top", {})
    local_state = competitor_state.get("local", {})
    with competitor_cols[0]:
        st.markdown("###### 業界トップ企業")
        top_state["name"] = st.text_input("企業名", value=str(top_state.get("name", "")))
        try:
            top_price_value = float(top_state.get("price", 0.0) or 0.0)
        except (TypeError, ValueError):
            top_price_value = 0.0
        top_state["price"] = st.number_input(
            "平均価格（円）",
            min_value=0.0,
            value=top_price_value,
            step=1000.0,
        )
        try:
            top_service_value = float(top_state.get("service_score", 3.0) or 3.0)
        except (TypeError, ValueError):
            top_service_value = 3.0
        top_state["service_score"] = st.number_input(
            "サービス差別化スコア (1-5)",
            min_value=1.0,
            max_value=5.0,
            value=top_service_value,
            step=0.1,
        )
        top_state["strengths"] = st.text_area(
            "強み",
            value=str(top_state.get("strengths", "")),
            height=110,
        )
        top_state["weaknesses"] = st.text_area(
            "弱み",
            value=str(top_state.get("weaknesses", "")),
            height=110,
        )
        top_state["differentiators"] = st.text_area(
            "差別化ポイント（数値・指標）",
            value=str(top_state.get("differentiators", "")),
            height=90,
            help="例：導入社数500社、稼働率99%、サポート拠点47都道府県など。",
        )
    with competitor_cols[1]:
        st.markdown("###### 地元・ニッチ競合")
        local_state["name"] = st.text_input("企業名 (地元)", value=str(local_state.get("name", "")))
        try:
            local_price_value = float(local_state.get("price", 0.0) or 0.0)
        except (TypeError, ValueError):
            local_price_value = 0.0
        local_state["price"] = st.number_input(
            "平均価格（円） (地元)",
            min_value=0.0,
            value=local_price_value,
            step=1000.0,
        )
        try:
            local_service_value = float(local_state.get("service_score", 3.0) or 3.0)
        except (TypeError, ValueError):
            local_service_value = 3.0
        local_state["service_score"] = st.number_input(
            "サービス差別化スコア (1-5) (地元)",
            min_value=1.0,
            max_value=5.0,
            value=local_service_value,
            step=0.1,
        )
        local_state["strengths"] = st.text_area(
            "強み (地元)",
            value=str(local_state.get("strengths", "")),
            height=110,
        )
        local_state["weaknesses"] = st.text_area(
            "弱み (地元)",
            value=str(local_state.get("weaknesses", "")),
            height=110,
        )
        local_state["differentiators"] = st.text_area(
            "差別化ポイント（数値・指標）(地元)",
            value=str(local_state.get("differentiators", "")),
            height=90,
        )

    recommendations = generate_marketing_recommendations(marketing_state, context_state)
    st.markdown("##### 自動生成された提案")
    st.caption("入力した4P/3C情報をもとに、強化策とポジショニングのヒントを提示します。")

    recommendation_cols = st.columns(2)
    four_p_suggestions = recommendations.get("four_p", {})
    with recommendation_cols[0]:
        for key in FOUR_P_KEYS[:2]:
            label = FOUR_P_LABELS[key]
            st.markdown(f"**{label}の強化策**")
            lines = four_p_suggestions.get(key, [])
            if lines:
                st.markdown("\n".join(f"- {line}" for line in lines))
            else:
                st.markdown("- 入力が不足しているため、提案を生成できません。")
    with recommendation_cols[1]:
        for key in FOUR_P_KEYS[2:]:
            label = FOUR_P_LABELS[key]
            st.markdown(f"**{label}の強化策**")
            lines = four_p_suggestions.get(key, [])
            if lines:
                st.markdown("\n".join(f"- {line}" for line in lines))
            else:
                st.markdown("- 入力が不足しているため、提案を生成できません。")

    st.markdown("**競合比較ハイライト**")
    competitor_highlights = recommendations.get("competitor_highlights", [])
    if competitor_highlights:
        st.markdown("\n".join(f"- {item}" for item in competitor_highlights))
    else:
        st.markdown("- 競合データが未入力のため、差分分析が表示できません。")

    st.markdown("**顧客価値提案 (UVP)**")
    st.write(recommendations.get("uvp", ""))
    st.markdown("**STP提案**")
    st.markdown(
        "\n".join(
            [
                f"- セグメンテーション: {recommendations.get('segmentation', '')}",
                f"- ターゲティング: {recommendations.get('targeting', '')}",
                f"- ポジショニング: {recommendations.get('positioning', '')}",
            ]
        )
    )
    positioning_points = recommendations.get("positioning_points", [])
    if positioning_points:
        st.markdown("\n".join(f"- {point}" for point in positioning_points))

    competitor_table = recommendations.get("competitor_table", [])
    if competitor_table:
        competitor_df = pd.DataFrame(competitor_table)
        st.dataframe(
            competitor_df,
            hide_index=True,
            **use_container_width_kwargs(st.dataframe),
        )

    st.markdown("#### SWOT分析（内部・外部要因の整理）")
    st.caption("強み・弱み・機会・脅威を1〜5段階で評価し、優先度の高い論点を定量的に把握します。")
    swot_editor_df = st.data_editor(
        st.session_state.get("swot_editor_df", _swot_editor_dataframe_from_state([])),
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "分類": st.column_config.SelectboxColumn(
                "分類",
                options=list(SWOT_CATEGORY_OPTIONS),
                help="Strength/Weakness/Opportunity/Threatから選択します。",
            ),
            "要因": st.column_config.TextColumn(
                "要因",
                help="例：独自アルゴリズムによる高い技術力など。1行に1項目で記入します。",
            ),
            "重要度(1-5)": st.column_config.NumberColumn(
                "重要度 (1-5)",
                min_value=1.0,
                max_value=5.0,
                step=0.5,
                format="%.1f",
                help="経営インパクトの大きさを評価します。5が最大。",
            ),
            "確度(1-5)": st.column_config.NumberColumn(
                "確度 (1-5)",
                min_value=1.0,
                max_value=5.0,
                step=0.5,
                format="%.1f",
                help="発生・維持の確度を評価します。5が確実。",
            ),
            "備考": st.column_config.TextColumn(
                "備考",
                help="補足メモや根拠、関連する指標を記入できます。",
            ),
        },
        key="swot_editor",
        **use_container_width_kwargs(st.data_editor),
    )
    st.session_state["swot_editor_df"] = swot_editor_df

    st.markdown("#### PEST分析（外部環境の変化）")
    st.caption(
        "政治(Political)・経済(Economic)・社会(Social)・技術(Technological)の外部要因と機会/脅威を評価します。"
    )
    pest_editor_df = st.data_editor(
        st.session_state.get("pest_editor_df", _pest_editor_dataframe_from_state([])),
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "区分": st.column_config.SelectboxColumn(
                "区分",
                options=list(PEST_DIMENSION_OPTIONS),
                help="PESTの区分を選択します。",
            ),
            "要因": st.column_config.TextColumn(
                "要因",
                help="例：補助金制度の拡充、金利上昇、消費者価値観の変化など。",
            ),
            "影響方向": st.column_config.SelectboxColumn(
                "影響方向",
                options=list(PEST_DIRECTION_OPTIONS),
                help="自社にとって機会か脅威かを選択します。",
            ),
            "影響度(1-5)": st.column_config.NumberColumn(
                "影響度 (1-5)",
                min_value=1.0,
                max_value=5.0,
                step=0.5,
                format="%.1f",
                help="ビジネスへの影響の大きさを評価します。",
            ),
            "確度(1-5)": st.column_config.NumberColumn(
                "確度 (1-5)",
                min_value=1.0,
                max_value=5.0,
                step=0.5,
                format="%.1f",
                help="要因が顕在化する確からしさを評価します。",
            ),
            "備考": st.column_config.TextColumn(
                "備考",
                help="情報源や想定シナリオなどを記載します。",
            ),
        },
        key="pest_editor",
        **use_container_width_kwargs(st.data_editor),
    )
    st.session_state["pest_editor_df"] = pest_editor_df

    current_analysis_state = dict(st.session_state.get(STRATEGIC_ANALYSIS_KEY, {}))
    current_analysis_state["swot"] = _records_from_swot_editor(swot_editor_df)
    current_analysis_state["pest"] = _records_from_pest_editor(pest_editor_df)
    st.session_state[STRATEGIC_ANALYSIS_KEY] = current_analysis_state

elif current_step == "sales":
    _maybe_show_tutorial("sales", "客数×単価×頻度の分解で売上を見積もると改善ポイントが見えます。")
    st.header("STEP 2｜売上計画")
    st.markdown("顧客セグメントとチャネルの整理結果をもとに、チャネル×商品×月で売上を見積もります。")
    st.info(
        "例：オンライン販売 10万円、店舗販売 5万円など具体的な数字から積み上げると精度が高まります。"
        "顧客数×客単価×購入頻度の分解を意識し、季節性やプロモーション施策も織り込みましょう。"
    )

    main_col, guide_col = st.columns([4, 1], gap="large")

    with main_col:
        _render_fermi_wizard(sales_df, unit)
        st.markdown("#### 業種テンプレート & オプション")
        template_options = ["—"] + list(INDUSTRY_TEMPLATES.keys())
        stored_template_key = str(st.session_state.get(INDUSTRY_TEMPLATE_KEY, ""))
        try:
            default_index = template_options.index(stored_template_key if stored_template_key else "—")
        except ValueError:
            default_index = 0

        template_cols = st.columns([2.5, 1.5])
        with template_cols[0]:
            selected_template_key = st.selectbox(
                "業種テンプレート",
                options=template_options,
                index=default_index,
                format_func=lambda key: (
                    "— 業種を選択 —"
                    if key == "—"
                    else INDUSTRY_TEMPLATES[key].label
                ),
                help="Fermi推定に基づく標準客数・単価・原価率を自動設定します。",
            )
            if selected_template_key != "—":
                template = INDUSTRY_TEMPLATES[selected_template_key]
                st.caption(template.description)
                with st.expander("テンプレートの前提を確認", expanded=False):
                    st.markdown(
                        "- 変動費率: "
                        + "、".join(
                            f"{code} {ratio:.1%}" for code, ratio in template.variable_ratios.items()
                        )
                    )
                    st.markdown(
                        "- 固定費 (月次換算): "
                        + "、".join(
                            f"{code} {format_amount_with_unit(Decimal(str(amount)) / Decimal('12'), '円')}"
                            for code, amount in template.fixed_costs.items()
                        )
                    )
                    st.markdown(
                        "- 運転資本想定 (回転日数): 売掛 {receivable:.0f}日 / 棚卸 {inventory:.0f}日 / 買掛 {payable:.0f}日".format(
                            receivable=template.working_capital.get("receivable_days", 45.0),
                            inventory=template.working_capital.get("inventory_days", 30.0),
                            payable=template.working_capital.get("payable_days", 25.0),
                        )
                    )
                    if template.custom_metrics:
                        st.markdown(
                            "- 業種特有KPI候補: "
                            + "、".join(template.custom_metrics.keys())
                        )
            else:
                template = None
        with template_cols[1]:
            st.write("")
            if st.button(
                "業種テンプレートを適用",
                type="secondary",
                **use_container_width_kwargs(st.button),
            ):
                if selected_template_key == "—":
                    st.warning("適用する業種を選択してください。")
                else:
                    _apply_industry_template(selected_template_key, unit_factor)
        if selected_template_key != "—":
            st.session_state[INDUSTRY_TEMPLATE_KEY] = selected_template_key

        control_cols = st.columns([1.2, 1.8, 1], gap="medium")
        with control_cols[0]:
            if st.button(
                "チャネル追加",
                key="add_channel_button",
                **use_container_width_kwargs(st.button),
            ):
                next_channel_idx = int(st.session_state.get(SALES_CHANNEL_COUNTER_KEY, 1))
                next_product_idx = int(st.session_state.get(SALES_PRODUCT_COUNTER_KEY, 1))
                new_row = {
                    "チャネル": f"新チャネル{next_channel_idx}",
                    "商品": f"新商品{next_product_idx}",
                    "想定顧客数": 0.0,
                    "客単価": 0.0,
                    "購入頻度(月)": 1.0,
                    "メモ": "",
                    **{month: 0.0 for month in MONTH_COLUMNS},
                }
                st.session_state[SALES_CHANNEL_COUNTER_KEY] = next_channel_idx + 1
                st.session_state[SALES_PRODUCT_COUNTER_KEY] = next_product_idx + 1
                updated = pd.concat([sales_df, pd.DataFrame([new_row])], ignore_index=True)
                st.session_state[SALES_TEMPLATE_STATE_KEY] = _standardize_sales_df(updated)
                st.toast("新しいチャネル行を追加しました。", icon="＋")

        channel_options = [str(ch) for ch in sales_df["チャネル"].tolist() if str(ch).strip()]
        if not channel_options:
            channel_options = [f"新チャネル{int(st.session_state.get(SALES_CHANNEL_COUNTER_KEY, 1))}"]
        with control_cols[1]:
            selected_channel = st.selectbox(
                "商品追加先チャネル",
                options=channel_options,
                key="product_channel_select",
                help="商品を追加するチャネルを選択します。",
            )
        with control_cols[2]:
            if st.button(
                "商品追加",
                key="add_product_button",
                **use_container_width_kwargs(st.button),
            ):
                next_product_idx = int(st.session_state.get(SALES_PRODUCT_COUNTER_KEY, 1))
                target_channel = selected_channel or channel_options[0]
                new_row = {
                    "チャネル": target_channel,
                    "商品": f"新商品{next_product_idx}",
                    "想定顧客数": 0.0,
                    "客単価": 0.0,
                    "購入頻度(月)": 1.0,
                    "メモ": "",
                    **{month: 0.0 for month in MONTH_COLUMNS},
                }
                st.session_state[SALES_PRODUCT_COUNTER_KEY] = next_product_idx + 1
                updated = pd.concat([sales_df, pd.DataFrame([new_row])], ignore_index=True)
                st.session_state[SALES_TEMPLATE_STATE_KEY] = _standardize_sales_df(updated)
                st.toast("選択したチャネルに商品行を追加しました。", icon="新")

        sales_df = st.session_state[SALES_TEMPLATE_STATE_KEY]
        month_columns_config = {
        month: st.column_config.NumberColumn(
            month,
            min_value=0.0,
            step=1.0,
            format="%.0f",
            help=f"月別の売上金額を入力します（単位：{unit}）。",
        )
        for month in MONTH_COLUMNS
    }
        guidance_col, preview_col = st.columns([2.6, 1.4], gap="large")
        with guidance_col:
            st.markdown("##### テンプレートの使い方")
            st.markdown(
                "\n".join(
                    f"- **{column}**：{description}"
                    for column, description in TEMPLATE_COLUMN_GUIDE
                )
            )
            st.caption("※ CSV/Excelでダウンロードしたテンプレートを編集し、そのままアップロードできます。")
            st.caption("※ アップロード時に必須列の欠損と数値形式を自動チェックします。")
            download_cols = st.columns(2)
            with download_cols[0]:
                st.download_button(
                    "CSVテンプレートDL",
                    data=_sales_template_to_csv(sales_df),
                    file_name="sales_template.csv",
                    mime="text/csv",
                    **use_container_width_kwargs(st.download_button),
                )
            with download_cols[1]:
                st.download_button(
                    "ExcelテンプレートDL",
                    data=_sales_template_to_excel(sales_df),
                    file_name="sales_template.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    **use_container_width_kwargs(st.download_button),
                )
            with st.form("sales_template_form"):
                uploaded_template = st.file_uploader(
                    "テンプレートをアップロード (最大5MB)",
                    type=["csv", "xlsx"],
                    accept_multiple_files=False,
                    help="ダウンロードしたテンプレートと同じ列構成でアップロードしてください。",
                )
                edited_df = st.data_editor(
                    sales_df,
                    num_rows="dynamic",
                    **use_container_width_kwargs(st.data_editor),
                    hide_index=True,
                    column_config={
                        "チャネル": st.column_config.TextColumn(
                            "チャネル", max_chars=40, help="販売経路（例：自社EC、店舗など）"
                        ),
                        "商品": st.column_config.TextColumn(
                            "商品", max_chars=40, help="商品・サービス名を入力します。"
                        ),
                        "想定顧客数": st.column_config.NumberColumn(
                            "想定顧客数", min_value=0.0, step=1.0, format="%d", help="月間で想定する顧客数。Fermi推定の起点となります。"
                        ),
                        "客単価": st.column_config.NumberColumn(
                            "客単価", min_value=0.0, step=100.0, format="%.0f", help="平均客単価。販促シナリオの前提になります。（単位：円）"
                        ),
                        "購入頻度(月)": st.column_config.NumberColumn(
                            "購入頻度(月)",
                            min_value=0.0,
                            step=0.1,
                            format="%.1f",
                            help="1ヶ月あたりの購入・利用回数。サブスクの場合は1.0を基準にします。",
                        ),
                        "メモ": st.column_config.TextColumn(
                            "メモ", max_chars=80, help="チャネル戦略や前提条件を記録します。"
                        ),
                        **month_columns_config,
                    },
                    key="sales_editor",
                )
                submit_kwargs = use_container_width_kwargs(st.form_submit_button)
                if st.form_submit_button("テンプレートを反映", **submit_kwargs):
                    try:
                        with st.spinner("テンプレートを反映しています..."):
                            if uploaded_template is not None:
                                loaded_df = _load_sales_template_from_upload(uploaded_template)
                                if loaded_df is not None:
                                    st.session_state[SALES_TEMPLATE_STATE_KEY] = loaded_df
                                    st.success("アップロードしたテンプレートを適用しました。")
                            else:
                                edited_frame = pd.DataFrame(edited_df)
                                issues = _validate_sales_template(edited_frame)
                                if issues:
                                    for issue in issues:
                                        st.error(issue)
                                else:
                                    st.session_state[SALES_TEMPLATE_STATE_KEY] = _standardize_sales_df(
                                        edited_frame
                                    )
                                    st.success("エディタの内容をテンプレートに反映しました。")
                    except Exception:
                        st.error(
                            "テンプレートの反映に失敗しました。列構成や数値を確認し、",
                            "解決しない場合は support@keieiplan.jp までお問い合わせください。",
                        )
        with preview_col:
            st.caption("テンプレートサンプル（1行のイメージ）")
            st.dataframe(
                _template_preview_dataframe(),
                hide_index=True,
                **use_container_width_kwargs(st.dataframe),
            )
        sales_df = st.session_state[SALES_TEMPLATE_STATE_KEY]
        with st.expander("外部データ連携・インポート", expanded=False):
            st.markdown(
                "会計ソフトやPOSから出力したCSV/Excelをアップロードすると、"
                "月次の実績データを自動集計し、予実分析やテンプレート更新に利用できます。"
            )
            source_type = st.selectbox(
                "データソース", ["会計ソフト", "POS", "銀行口座CSV", "その他"], key="external_source_type"
            )
            uploaded_external = st.file_uploader(
                "CSV / Excelファイル", type=["csv", "xlsx"], key="external_import_file"
            )
            external_df: pd.DataFrame | None = None
            if uploaded_external is not None:
                try:
                    if uploaded_external.name.lower().endswith(".xlsx"):
                        external_df = pd.read_excel(uploaded_external)
                    else:
                        external_df = pd.read_csv(uploaded_external)
                except Exception:
                    external_df = None
                    st.error("ファイルの読み込みに失敗しました。列構成を確認してください。")

            if external_df is not None and not external_df.empty:
                st.dataframe(
                    external_df.head(20),
                    hide_index=True,
                    **use_container_width_kwargs(st.dataframe),
                )
                columns = list(external_df.columns)
                date_col = st.selectbox("日付列", columns, key="external_date_col")
                amount_col = st.selectbox("金額列", columns, key="external_amount_col")
                category_options = ["指定しない", *columns]
                category_col = st.selectbox(
                    "区分列 (任意)", category_options, index=0, key="external_category_col"
                )
                target_metric = st.selectbox(
                    "取り込み先", ["売上", "変動費", "固定費"], key="external_target_metric"
                )

                working_df = external_df[[date_col, amount_col]].copy()
                working_df["__date"] = pd.to_datetime(working_df[date_col], errors="coerce")
                working_df["__amount"] = pd.to_numeric(working_df[amount_col], errors="coerce")
                if category_col != "指定しない":
                    working_df["__category"] = external_df[category_col].astype(str)
                    categories = (
                        working_df["__category"].dropna().unique().tolist()
                        if not working_df["__category"].dropna().empty
                        else []
                    )
                    selected_categories = st.multiselect(
                        "対象カテゴリ", categories, default=categories, key="external_category_filter"
                    )
                    if selected_categories:
                        working_df = working_df[working_df["__category"].isin(selected_categories)]
                else:
                    selected_categories = None

                working_df = working_df.dropna(subset=["__date", "__amount"])
                if working_df.empty:
                    st.warning("有効な日付と金額の行が見つかりませんでした。")
                else:
                    working_df["__month"] = working_df["__date"].dt.month
                    monthly_totals = working_df.groupby("__month")["__amount"].sum()
                    monthly_map = {
                        month: float(monthly_totals.get(month, 0.0)) for month in MONTH_SEQUENCE
                    }
                    monthly_table = pd.DataFrame(
                        {
                            "月": [f"{month}月" for month in MONTH_SEQUENCE],
                            "金額": [monthly_map[month] for month in MONTH_SEQUENCE],
                        }
                    )
                    st.dataframe(
                        monthly_table,
                        hide_index=True,
                        **use_container_width_kwargs(st.dataframe),
                    )
                    total_amount = float(sum(monthly_map.values()))
                    st.metric("年間合計", format_amount_with_unit(Decimal(str(total_amount)), "円"))

                    apply_to_plan = False
                    selected_fixed_code: str | None = None
                    if target_metric == "固定費":
                        apply_to_plan = st.checkbox(
                            "平均月額を固定費に反映する", value=True, key="external_apply_fixed"
                        )
                        fixed_options = [code for code, _, _, _ in FIXED_COST_FIELDS]
                        selected_fixed_code = st.selectbox(
                            "反映先の固定費項目",
                            fixed_options,
                            format_func=lambda code: next(
                                label
                                for code_, label, _, _ in FIXED_COST_FIELDS
                                if code_ == code
                            ),
                            key="external_fixed_code",
                        )
                    elif target_metric == "売上":
                        apply_to_plan = st.checkbox(
                            "テンプレートに売上行を追加", value=False, key="external_apply_sales"
                        )
                    else:
                        st.caption("変動費は実績データとして保存し、分析ページで原価率を確認します。")

                    if st.button("実績データを保存", key="external_import_apply"):
                        actual_key_map = {
                            "売上": "sales",
                            "変動費": "variable_costs",
                            "固定費": "fixed_costs",
                        }
                        actuals_state = st.session_state.get("external_actuals", {})
                        actuals_state[actual_key_map[target_metric]] = {
                            "monthly": monthly_map,
                            "source": source_type,
                            "file_name": getattr(uploaded_external, "name", ""),
                            "category": selected_categories,
                            "total": total_amount,
                        }
                        st.session_state["external_actuals"] = actuals_state

                        plan_total_decimal = _calculate_sales_total(
                            _standardize_sales_df(pd.DataFrame(st.session_state[SALES_TEMPLATE_STATE_KEY]))
                        )
                        _update_fermi_learning(plan_total_decimal, Decimal(str(total_amount)))

                        if apply_to_plan and target_metric == "売上":
                            new_row = {
                                "チャネル": f"{source_type}連携",
                                "商品": "外部実績",
                                "想定顧客数": 0.0,
                                "客単価": 0.0,
                                "購入頻度(月)": 1.0,
                                "メモ": "外部実績データ",
                                **{f"月{month:02d}": monthly_map[month] for month in MONTH_COLUMNS},
                            }
                            updated = pd.concat(
                                [st.session_state[SALES_TEMPLATE_STATE_KEY], pd.DataFrame([new_row])],
                                ignore_index=True,
                            )
                            st.session_state[SALES_TEMPLATE_STATE_KEY] = _standardize_sales_df(updated)
                            st.toast("外部データを売上テンプレートに追加しました。", icon="収")
                        if apply_to_plan and target_metric == "固定費" and selected_fixed_code:
                            monthly_average = Decimal(str(total_amount)) / Decimal(len(MONTH_SEQUENCE))
                            st.session_state[f"fixed_cost_{selected_fixed_code}"] = float(
                                monthly_average / (unit_factor or Decimal("1"))
                            )
                            st.toast("固定費を実績平均で更新しました。", icon="資")
                        st.success("実績データを保存しました。分析ページで予実差異が表示されます。")
            elif uploaded_external is not None:
                st.warning("読み込めるデータがありません。サンプル行を確認してください。")

        if any(err.field.startswith("sales") for err in validation_errors):
            messages = "<br/>".join(
                err.message for err in validation_errors if err.field.startswith("sales")
            )
            st.markdown(f"<div class='field-error'>{messages}</div>", unsafe_allow_html=True)

    with guide_col:
        _render_sales_guide_panel()

elif current_step == "costs":
    _maybe_show_tutorial("costs", "原価率と固定費のレンジを設定し、利益感度を把握しましょう。")
    st.header("STEP 3｜原価・経費")
    st.markdown("売上に対する変動費（原価）と固定費、営業外項目を入力し、粗利益率の前提を確認します。")
    st.info("粗利益率＝(売上−売上原価)÷売上。製造業では30%を超えると優良とされます。目標レンジと比較しながら設定しましょう。")

    st.markdown("#### 変動費（原価率）")
    var_cols = st.columns(len(VARIABLE_RATIO_FIELDS))
    variable_inputs: Dict[str, float] = {}
    for col, (code, label, help_text) in zip(var_cols, VARIABLE_RATIO_FIELDS):
        with col:
            variable_inputs[code] = _percent_number_input(
                label,
                min_value=0.0,
                max_value=1.0,
                step=0.005,
                value=float(variable_ratios.get(code, 0.0)),
                key=f"var_ratio_{code}",
                help=help_text,
            )
    st.caption("※ 原価率は売上高に対する比率で入力します。0〜100%の範囲で設定してください。")

    st.markdown("#### 固定費・販管費")
    fixed_inputs: Dict[str, float] = {}
    for category in ("固定費", "販管費"):
        grouped_fields = [
            field for field in FIXED_COST_FIELDS if FIXED_COST_CATEGORY.get(field[0]) == category
        ]
        if not grouped_fields:
            continue
        st.markdown(f"##### {category}")
        fixed_cols = st.columns(len(grouped_fields))
        for col, (code, label, _, help_text) in zip(fixed_cols, grouped_fields):
            with col:
                base_value = Decimal(str(fixed_costs.get(code, 0.0)))
                fixed_inputs[code] = _yen_number_input(
                    f"{label} ({unit})",
                    value=float(base_value / unit_factor),
                    step=1.0,
                    key=f"fixed_cost_{code}",
                    help=help_text,
                )
    st.caption("※ 表示単位に合わせた金額で入力します。採用計画やコスト削減メモは事業計画メモ欄へ。")

    st.markdown("#### 営業外収益 / 営業外費用")
    noi_cols = st.columns(len(NOI_FIELDS))
    noi_inputs: Dict[str, float] = {}
    for col, (code, label, help_text) in zip(noi_cols, NOI_FIELDS):
        with col:
            base_value = Decimal(str(noi_defaults.get(code, 0.0)))
            noi_inputs[code] = _yen_number_input(
                f"{label} ({unit})",
                value=float(base_value / unit_factor),
                step=1.0,
                key=f"noi_{code}",
                help=help_text,
            )

    noe_cols = st.columns(len(NOE_FIELDS))
    noe_inputs: Dict[str, float] = {}
    for col, (code, label, help_text) in zip(noe_cols, NOE_FIELDS):
        with col:
            base_value = Decimal(str(noe_defaults.get(code, 0.0)))
            noe_inputs[code] = _yen_number_input(
                f"{label} ({unit})",
                value=float(base_value / unit_factor),
                step=1.0,
                key=f"noe_{code}",
                help=help_text,
            )

    st.markdown("#### 売上総利益率への影響")
    total_sales_amount = float(_calculate_sales_total(sales_df))
    impact_records: List[Dict[str, float | str]] = []
    order_index = 0
    var_total_pct = 0.0
    for code, label, _ in VARIABLE_RATIO_FIELDS:
        ratio_pct = variable_inputs.get(code, 0.0) * 100.0
        if ratio_pct <= 0:
            continue
        impact_records.append(
            {
                "項目": label.replace(" (％)", ""),
                "区分": "変動費",
                "影響度": -ratio_pct,
                "順序": order_index,
            }
        )
        order_index += 1
        var_total_pct += ratio_pct
    gross_margin_pct = max(-200.0, min(100.0, 100.0 - var_total_pct))
    impact_records.append(
        {
            "項目": "売上総利益率",
            "区分": "利益率",
            "影響度": gross_margin_pct,
            "順序": order_index,
        }
    )
    order_index += 1

    fixed_total_pct = 0.0
    if total_sales_amount > 0:
        unit_multiplier = float(unit_factor or Decimal("1"))
        for code, label, category, _ in FIXED_COST_FIELDS:
            amount = float(fixed_inputs.get(code, 0.0)) * unit_multiplier
            pct = (amount / total_sales_amount) * 100.0 if total_sales_amount else 0.0
            if pct <= 0:
                continue
            impact_records.append(
                {
                    "項目": label,
                    "区分": category,
                    "影響度": -pct,
                    "順序": order_index,
                }
            )
            order_index += 1
            fixed_total_pct += pct
        operating_margin_pct = gross_margin_pct - fixed_total_pct
        impact_records.append(
            {
                "項目": "営業利益率",
                "区分": "利益率",
                "影響度": operating_margin_pct,
                "順序": order_index,
            }
        )
    else:
        st.info("売上計画が未入力のため、粗利率のチャートは売上データ登録後に表示されます。")

    if impact_records and total_sales_amount > 0:
        impact_df = pd.DataFrame(impact_records)
        sort_order = impact_df.sort_values("順序")
        chart = (
            alt.Chart(sort_order)
            .mark_bar()
            .encode(
                x=alt.X(
                    "影響度:Q",
                    axis=alt.Axis(format="+.1f", title="売上に対する割合 (％)"),
                ),
                y=alt.Y(
                    "項目:N",
                    sort=alt.SortField(field="順序", order="ascending"),
                ),
                color=alt.Color("区分:N", legend=alt.Legend(title="区分")),
                tooltip=[
                    alt.Tooltip("項目:N"),
                    alt.Tooltip("区分:N"),
                    alt.Tooltip("影響度:Q", format="+.1f"),
                ],
            )
            .properties(height=280)
        )
        st.altair_chart(chart, use_container_width=True)
    elif total_sales_amount > 0:
        st.info("コスト項目が0のため、粗利率チャートを描画できるデータがありません。")

    cost_range_state: Dict[str, Dict[str, float]] = st.session_state.get(COST_RANGE_STATE_KEY, {})
    with st.expander("調 レンジ入力 (原価・費用の幅)", expanded=False):
        st.caption("最小・中央値・最大の3点を入力すると、分析ページで感度レンジを参照できます。")

        variable_rows = []
        for code, label, _ in VARIABLE_RATIO_FIELDS:
            profile = cost_range_state.get(code, {})
            variable_rows.append(
                {
                    "コード": code,
                    "項目": label,
                    "最小 (％)": float(profile.get("min", variable_inputs.get(code, 0.0))) * 100.0,
                    "中央値 (％)": float(
                        profile.get("typical", variable_inputs.get(code, 0.0))
                    )
                    * 100.0,
                    "最大 (％)": float(profile.get("max", variable_inputs.get(code, 0.0))) * 100.0,
                }
            )
        variable_range_df = pd.DataFrame(variable_rows)
        variable_edited = st.data_editor(
            variable_range_df,
            hide_index=True,
            column_config={
                "コード": st.column_config.TextColumn("コード", disabled=True),
                "項目": st.column_config.TextColumn("項目", disabled=True),
                "最小 (％)": st.column_config.NumberColumn(
                    "最小 (％)", min_value=0.0, max_value=100.0, format="%.1f", help="％で入力"
                ),
                "中央値 (％)": st.column_config.NumberColumn(
                    "中央値 (％)", min_value=0.0, max_value=100.0, format="%.1f", help="％で入力"
                ),
                "最大 (％)": st.column_config.NumberColumn(
                    "最大 (％)", min_value=0.0, max_value=100.0, format="%.1f", help="％で入力"
                ),
            },
            key="cost_variable_range_editor",
            **use_container_width_kwargs(st.data_editor),
        )
        _update_cost_range_state_from_editor(variable_edited)

        fixed_rows = []
        for code, label, _, _ in FIXED_COST_FIELDS:
            profile = cost_range_state.get(code, {})
            fixed_rows.append(
                {
                    "コード": code,
                    "項目": label,
                    "最小": float(profile.get("min", fixed_inputs.get(code, 0.0))),
                    "中央値": float(profile.get("typical", fixed_inputs.get(code, 0.0))),
                    "最大": float(profile.get("max", fixed_inputs.get(code, 0.0))),
                }
            )
        for code, label, _ in NOI_FIELDS + NOE_FIELDS:
            profile = cost_range_state.get(code, {})
            base_value = noi_inputs.get(code) if code in noi_inputs else noe_inputs.get(code, 0.0)
            fixed_rows.append(
                {
                    "コード": code,
                    "項目": label,
                    "最小": float(profile.get("min", base_value)),
                    "中央値": float(profile.get("typical", base_value)),
                    "最大": float(profile.get("max", base_value)),
                }
            )
        fixed_range_df = pd.DataFrame(fixed_rows)
        fixed_edited = st.data_editor(
            fixed_range_df,
            hide_index=True,
            column_config={
                "コード": st.column_config.TextColumn("コード", disabled=True),
                "項目": st.column_config.TextColumn("項目", disabled=True),
                "最小": st.column_config.NumberColumn(
                    "最小", min_value=0.0, format="%.0f", help=f"単位：{unit}"
                ),
                "中央値": st.column_config.NumberColumn(
                    "中央値", min_value=0.0, format="%.0f", help=f"単位：{unit}"
                ),
                "最大": st.column_config.NumberColumn(
                    "最大", min_value=0.0, format="%.0f", help=f"単位：{unit}"
                ),
            },
            key="cost_fixed_range_editor",
            **use_container_width_kwargs(st.data_editor),
        )
        _update_cost_range_state_from_editor(fixed_edited)

    if any(err.field.startswith("costs") for err in validation_errors):
        messages = "<br/>".join(
            err.message for err in validation_errors if err.field.startswith("costs")
        )
        st.markdown(f"<div class='field-error'>{messages}</div>", unsafe_allow_html=True)

elif current_step == "invest":
    _maybe_show_tutorial("invest", "投資と借入のタイミングを整理すると資金繰りが読みやすくなります。")
    st.header("STEP 4｜投資・借入")
    st.markdown("成長投資や資金調達のスケジュールを設定します。金額・開始月・耐用年数を明確にしましょう。")
    st.info("投資額は税込・税抜どちらでも構いませんが、他データと整合するよう統一します。借入は金利・返済期間・開始月をセットで管理しましょう。")

    st.markdown("#### 設備投資 (Capex)")
    current_capex_df = pd.DataFrame(st.session_state.get("capex_editor_df", capex_defaults_df))
    capex_editor_df = st.data_editor(
        current_capex_df,
        num_rows="dynamic",
        **use_container_width_kwargs(st.data_editor),
        hide_index=True,
        column_config={
            "投資名": st.column_config.TextColumn("投資名", help="投資対象の名称を入力します。"),
            "金額": st.column_config.NumberColumn(
                "金額 (円)",
                min_value=0.0,
                step=1_000_000.0,
                format="%.0f",
                help="投資にかかる総額。例：5,000,000円など。",
            ),
            "開始月": st.column_config.NumberColumn(
                "開始月",
                min_value=1,
                max_value=12,
                step=1,
                help="設備が稼働を開始する月。",
            ),
            "耐用年数": st.column_config.NumberColumn(
                "耐用年数 (年)",
                min_value=1,
                max_value=20,
                step=1,
                help="減価償却に用いる耐用年数を入力します。",
            ),
        },
        key="capex_editor",
    )
    st.session_state["capex_editor_df"] = capex_editor_df
    st.caption("例：新工場設備 5,000,000円を4月開始、耐用年数5年 など。")

    st.markdown("#### 借入スケジュール")
    current_loan_df = pd.DataFrame(st.session_state.get("loan_editor_df", loan_defaults_df))
    loan_editor_df = st.data_editor(
        current_loan_df,
        num_rows="dynamic",
        **use_container_width_kwargs(st.data_editor),
        hide_index=True,
        column_config={
            "名称": st.column_config.TextColumn("名称", help="借入の名称（例：メインバンク、リースなど）。"),
            "元本": st.column_config.NumberColumn(
                "元本 (円)",
                min_value=0.0,
                step=1_000_000.0,
                format="%.0f",
                help="借入金額の総額。",
            ),
            "金利": st.column_config.NumberColumn(
                "金利",
                min_value=0.0,
                max_value=0.2,
                step=0.001,
                format="%.2f",
                help="年利ベースの金利を入力します（例：5%の場合は0.05）。",
            ),
            "返済期間(月)": st.column_config.NumberColumn(
                "返済期間 (月)",
                min_value=1,
                max_value=600,
                step=1,
                help="返済回数（月数）。",
            ),
            "開始月": st.column_config.NumberColumn(
                "開始月",
                min_value=1,
                max_value=12,
                step=1,
                help="返済開始月。",
            ),
            "返済タイプ": st.column_config.SelectboxColumn(
                "返済タイプ",
                options=["equal_principal", "interest_only"],
                help="元金均等（equal_principal）か利息のみ（interest_only）かを選択。",
            ),
        },
        key="loan_editor",
    )
    st.session_state["loan_editor_df"] = loan_editor_df

    capex_payload = _serialize_capex_editor_df(capex_editor_df)
    loan_payload = _serialize_loan_editor_df(loan_editor_df)

    capex_preview: CapexPlan | None
    loan_preview: LoanSchedule | None
    try:
        capex_preview = CapexPlan(**capex_payload)
    except ValidationError:
        capex_preview = None
    try:
        loan_preview = LoanSchedule(**loan_payload)
    except ValidationError:
        loan_preview = None

    st.markdown("#### 入力内容のプレビュー")
    preview_cols = st.columns(2)
    with preview_cols[0]:
        st.markdown("##### 設備投資スケジュール")
        if capex_preview and capex_preview.items:
            capex_rows = [
                {
                    "投資名": payment.name,
                    "支払タイミング": f"FY{int(payment.year)} 月{int(payment.month):02d}",
                    "支払額": format_amount_with_unit(payment.amount, "円"),
                }
                for payment in capex_preview.payment_schedule()
            ]
            capex_preview_df = pd.DataFrame(capex_rows)
            st.dataframe(
                capex_preview_df,
                hide_index=True,
                **use_container_width_kwargs(st.dataframe),
            )
        else:
            st.info("正の金額で投資を入力するとここにスケジュールが表示されます。")
    with preview_cols[1]:
        st.markdown("##### 借入返済表 (初期) ")
        if loan_preview and loan_preview.loans:
            amortization = loan_preview.amortization_schedule()
            preview_rows = [
                {
                    "ローン": entry.loan_name,
                    "時期": f"FY{int(entry.year)} 月{int(entry.month):02d}",
                    "利息": format_amount_with_unit(entry.interest, "円"),
                    "元金": format_amount_with_unit(entry.principal, "円"),
                    "残高": format_amount_with_unit(entry.balance, "円"),
                }
                for entry in amortization[:36]
            ]
            loan_preview_df = pd.DataFrame(preview_rows)
            st.dataframe(
                loan_preview_df,
                hide_index=True,
                **use_container_width_kwargs(st.dataframe),
            )
            if len(amortization) > 36:
                st.caption("※ 37ヶ月目以降はAnalysisタブの詳細スケジュールで確認できます。")
        else:
            st.info("元本・金利・返済期間を入力すると返済スケジュールを自動計算します。")

    preview_cf_data: Dict[str, object] | None = None
    preview_issues: List[ValidationIssue] = []
    if capex_preview and loan_preview:
        preview_raw = dict(finance_raw)
        preview_raw["capex"] = capex_payload
        preview_raw["loans"] = loan_payload
        preview_bundle, preview_issues = validate_bundle(preview_raw)
        if preview_bundle:
            fte_value = Decimal(str(settings_state.get("fte", 20)))
            plan_preview = plan_from_models(
                preview_bundle.sales,
                preview_bundle.costs,
                preview_bundle.capex,
                preview_bundle.loans,
                preview_bundle.tax,
                fte=fte_value,
                unit=unit,
            )
            preview_amounts = compute(plan_preview)
            preview_cf_data = generate_cash_flow(
                preview_amounts,
                preview_bundle.capex,
                preview_bundle.loans,
                preview_bundle.tax,
            )

    if preview_cf_data and isinstance(preview_cf_data, dict):
        metrics_preview = preview_cf_data.get("investment_metrics", {})
        if isinstance(metrics_preview, dict) and metrics_preview.get("monthly_cash_flows"):
            st.markdown("#### 投資評価プレビュー")
            payback_val = metrics_preview.get("payback_period_years")
            npv_val = Decimal(str(metrics_preview.get("npv", Decimal("0"))))
            discount_val = Decimal(str(metrics_preview.get("discount_rate", Decimal("0"))))
            metric_cols = st.columns(3)
            with metric_cols[0]:
                payback_text = "—"
                if payback_val is not None:
                    payback_text = f"{float(Decimal(str(payback_val))):.1f}年"
                st.metric("投資回収期間", payback_text)
            with metric_cols[1]:
                st.metric("NPV", format_amount_with_unit(npv_val, "円"))
            with metric_cols[2]:
                st.metric("割引率", f"{float(discount_val) * 100:.1f}%")
    elif preview_issues:
        st.info("他のステップに未入力またはエラーがあるため、投資指標の試算は保存後に計算されます。")

    if any(err.field.startswith("capex") for err in validation_errors):
        messages = "<br/>".join(
            err.message for err in validation_errors if err.field.startswith("capex")
        )
        st.markdown(f"<div class='field-error'>{messages}</div>", unsafe_allow_html=True)
    if any(err.field.startswith("loans") for err in validation_errors):
        messages = "<br/>".join(
            err.message for err in validation_errors if err.field.startswith("loans")
        )
        st.markdown(f"<div class='field-error'>{messages}</div>", unsafe_allow_html=True)

elif current_step == "tax":
    _maybe_show_tutorial("tax", "保存ボタンで計画を確定し、各ページへ反映させましょう。")
    st.header("STEP 5｜税制・保存")
    st.markdown("税率を確認し、これまでの入力内容を保存します。")
    st.info(
        "所得税・法人税率や事業税率、消費税率は業種や制度により異なります。最新情報を確認しながら設定してください。"
    )

    tax_cols = st.columns(4)
    with tax_cols[0]:
        corporate_rate = _percent_number_input(
            "所得税・法人税率 (0-55%)",
            min_value=0.0,
            max_value=0.55,
            step=0.01,
            value=float(st.session_state.get("tax_corporate_rate", 0.3)),
            key="tax_corporate_rate",
            help=TAX_FIELD_META["corporate"],
        )
    with tax_cols[1]:
        business_rate = _percent_number_input(
            "事業税率 (0-15%)",
            min_value=0.0,
            max_value=0.15,
            step=0.005,
            value=float(st.session_state.get("tax_business_rate", 0.05)),
            key="tax_business_rate",
            help=TAX_FIELD_META["business"],
        )
    with tax_cols[2]:
        consumption_rate = _percent_number_input(
            "消費税率 (0-20%)",
            min_value=0.0,
            max_value=0.20,
            step=0.01,
            value=float(st.session_state.get("tax_consumption_rate", 0.1)),
            key="tax_consumption_rate",
            help=TAX_FIELD_META["consumption"],
        )
    with tax_cols[3]:
        dividend_ratio = _percent_number_input(
            "配当性向",
            min_value=0.0,
            max_value=1.0,
            step=0.05,
            value=float(st.session_state.get("tax_dividend_ratio", 0.0)),
            key="tax_dividend_ratio",
            help=TAX_FIELD_META["dividend"],
        )

    sales_df = _standardize_sales_df(pd.DataFrame(st.session_state[SALES_TEMPLATE_STATE_KEY]))
    total_sales = sum(
        Decimal(str(row[month])) for _, row in sales_df.iterrows() for month in MONTH_COLUMNS
    )
    current_variable_inputs = _variable_inputs_from_state(variable_ratios)
    avg_ratio = (
        sum(current_variable_inputs.values()) / len(current_variable_inputs)
        if current_variable_inputs
        else 0.0
    )

    metric_cols = st.columns(2)
    with metric_cols[0]:
        st.markdown(
            f"<div class='metric-card' title='年間のチャネル×商品売上の合計額です。'>¥ <strong>売上合計</strong><br/><span style='font-size:1.4rem;'>{format_amount_with_unit(total_sales, unit)}</span></div>",
            unsafe_allow_html=True,
        )
    with metric_cols[1]:
        st.markdown(
            f"<div class='metric-card' title='粗利益率＝(売上−売上原価)÷売上。製造業では30%を超えると優良とされます。'>↗ <strong>平均原価率</strong><br/><span style='font-size:1.4rem;'>{format_ratio(avg_ratio)}</span></div>",
            unsafe_allow_html=True,
        )

    fiscal_year = int(settings_state.get("fiscal_year", datetime.now().year))
    st.markdown("#### 財務指標（実績・計画）入力")
    st.caption(
        "過去3年分の実績と今後5年分の計画値を入力してください。粗利益率・営業利益率は百分率（例：40 → 40%）で入力します。"
    )
    financial_editor_df = _load_financial_timeseries_df(fiscal_year)
    financial_column_config = {
        "年度": st.column_config.NumberColumn(
            "年度",
            format="%d",
            min_value=2000,
            max_value=2100,
            step=1,
            help="会計年度。必要に応じて修正できます。",
        ),
        "区分": st.column_config.SelectboxColumn(
            "区分",
            options=list(FINANCIAL_CATEGORY_OPTIONS),
            help="過年度は実績、将来は計画を選択します。",
        ),
        "売上高": st.column_config.NumberColumn(
            "売上高 (円)",
            format="%.0f",
            help="各年度の売上高。単位は円です。",
        ),
        "粗利益率": st.column_config.NumberColumn(
            "粗利益率(%)",
            format="%.1f",
            help="粗利益率を百分率で入力します (例: 40 → 40%)。",
        ),
        "営業利益率": st.column_config.NumberColumn(
            "営業利益率(%)",
            format="%.1f",
            help="営業利益率を百分率で入力します。",
        ),
        "固定費": st.column_config.NumberColumn(
            "固定費 (円)",
            format="%.0f",
            help="人件費や地代などの年間固定費。",
        ),
        "変動費": st.column_config.NumberColumn(
            "変動費 (円)",
            format="%.0f",
            help="仕入原価などの年間変動費。",
        ),
        "設備投資額": st.column_config.NumberColumn(
            "設備投資額 (円)",
            format="%.0f",
            help="当該年度に予定するCAPEX。",
        ),
        "借入残高": st.column_config.NumberColumn(
            "借入残高 (円)",
            format="%.0f",
            help="決算時点の有利子負債残高。",
        ),
        "減価償却費": st.column_config.NumberColumn(
            "減価償却費 (円)",
            format="%.0f",
            help="任意入力。EBITDA算出に利用します。",
        ),
        "総資産": st.column_config.NumberColumn(
            "総資産 (円)",
            format="%.0f",
            help="任意入力。ROA計算に利用します。",
        ),
    }

    edited_financial_df = st.data_editor(
        financial_editor_df,
        key="financial_timeseries_editor",
        hide_index=True,
        num_rows="dynamic",
        use_container_width=True,
        column_config=financial_column_config,
    )
    _persist_financial_timeseries(edited_financial_df, fiscal_year)
    st.caption(
        "金額は円ベースで入力してください。EBITDA・FCF・ROAなどの自動計算結果はAnalysisページで確認できます。"
    )

    if validation_errors:
        st.warning("入力内容にエラーがあります。該当ステップに戻って赤枠の項目を修正してください。")

    costs_variable_inputs = _variable_inputs_from_state(variable_ratios)
    costs_fixed_inputs = _monetary_inputs_from_state(
        fixed_costs, FIXED_COST_FIELDS, "fixed_cost", unit_factor
    )
    costs_noi_inputs = _monetary_inputs_from_state(
        noi_defaults, NOI_FIELDS, "noi", unit_factor
    )
    costs_noe_inputs = _monetary_inputs_from_state(
        noe_defaults, NOE_FIELDS, "noe", unit_factor
    )

    tax_payload = {
        "corporate_tax_rate": Decimal(str(corporate_rate)),
        "business_tax_rate": Decimal(str(business_rate)),
        "consumption_tax_rate": Decimal(str(consumption_rate)),
        "dividend_payout_ratio": Decimal(str(dividend_ratio)),
    }
    capex_df_current = pd.DataFrame(st.session_state.get("capex_editor_df", capex_defaults_df))
    loan_df_current = pd.DataFrame(st.session_state.get("loan_editor_df", loan_defaults_df))
    cost_range_state = st.session_state.get(COST_RANGE_STATE_KEY, {})

    bundle_payload = _build_bundle_payload_from_inputs(
        sales_df,
        costs_variable_inputs,
        costs_fixed_inputs,
        costs_noi_inputs,
        costs_noe_inputs,
        unit_factor=unit_factor,
        cost_range_state=cost_range_state,
        capex_df=capex_df_current,
        loan_df=loan_df_current,
        tax_payload=tax_payload,
    )
    preview_bundle, preview_issues = validate_bundle(bundle_payload)

    preview_amounts: Dict[str, Decimal] = {}
    preview_cf_data: Dict[str, object] | None = None
    if preview_bundle:
        fte_value = Decimal(str(settings_state.get("fte", 20)))
        plan_preview = plan_from_models(
            preview_bundle.sales,
            preview_bundle.costs,
            preview_bundle.capex,
            preview_bundle.loans,
            preview_bundle.tax,
            fte=fte_value,
            unit=unit,
        )
        preview_amounts = compute(plan_preview)
        preview_cf_data = generate_cash_flow(
            preview_amounts,
            preview_bundle.capex,
            preview_bundle.loans,
            preview_bundle.tax,
        )

    if preview_bundle and preview_amounts:
        st.markdown("#### 年間税額の試算")
        ordinary_income = Decimal(str(preview_amounts.get("ORD", Decimal("0"))))
        sales_total_decimal = Decimal(str(preview_amounts.get("REV", Decimal("0"))))
        taxable_expense_total = sum(
            Decimal(str(preview_amounts.get(code, Decimal("0"))))
            for code in CONSUMPTION_TAX_DEDUCTIBLE_CODES
        )
        tax_policy = TaxPolicy.model_validate(preview_bundle.tax)
        income_breakdown = tax_policy.income_tax_components(ordinary_income)
        consumption_breakdown = tax_policy.consumption_tax_balance(
            sales_total_decimal,
            taxable_expense_total,
        )
        consumption_base = sales_total_decimal - taxable_expense_total
        total_tax = income_breakdown["total"] + consumption_breakdown["net"]
        tax_df = pd.DataFrame(
            [
                {
                    "税目": "所得税・法人税",
                    "課税ベース": format_amount_with_unit(ordinary_income, unit),
                    "税率": format_ratio(tax_policy.corporate_tax_rate),
                    "想定納税額": format_amount_with_unit(income_breakdown["corporate"], unit),
                },
                {
                    "税目": "事業税",
                    "課税ベース": format_amount_with_unit(ordinary_income, unit),
                    "税率": format_ratio(tax_policy.business_tax_rate),
                    "想定納税額": format_amount_with_unit(income_breakdown["business"], unit),
                },
                {
                    "税目": "消費税 (純額)",
                    "課税ベース": format_amount_with_unit(consumption_base, unit),
                    "税率": format_ratio(tax_policy.consumption_tax_rate),
                    "想定納税額": format_amount_with_unit(consumption_breakdown["net"], unit),
                },
                {
                    "税目": "年間合計",
                    "課税ベース": "—",
                    "税率": "—",
                    "想定納税額": format_amount_with_unit(total_tax, unit),
                },
            ]
        )
        st.dataframe(
            tax_df,
            hide_index=True,
            **use_container_width_kwargs(st.dataframe),
            column_config={
                "税目": st.column_config.TextColumn("税目"),
                "課税ベース": st.column_config.TextColumn("課税ベース"),
                "税率": st.column_config.TextColumn("税率"),
                "想定納税額": st.column_config.TextColumn("想定納税額"),
            },
        )
        if consumption_breakdown["net"] < Decimal("0"):
            st.caption("※ 消費税は仕入控除が上回るため還付見込み（マイナス表示）です。")
        st.caption(f"金額は{unit}単位で表示しています。")

        metrics_preview = preview_cf_data.get("investment_metrics", {}) if preview_cf_data else {}
        monthly_projection = metrics_preview.get("monthly_cash_flows", [])
        if monthly_projection:
            st.markdown("#### 月次資金繰りシミュレーション")
            monthly_df = pd.DataFrame(monthly_projection)
            if not monthly_df.empty:
                scaling = unit_factor or Decimal("1")

                def _to_decimal_safe(value: object) -> Decimal:
                    try:
                        return Decimal(str(value))
                    except Exception:
                        return Decimal("0")

                display_df = pd.DataFrame(
                    {
                        "年": monthly_df["year"].apply(lambda x: int(_to_decimal_safe(x))),
                        "月": monthly_df["month"].apply(lambda x: int(_to_decimal_safe(x))),
                        "営業CF": monthly_df["operating"].apply(
                            lambda x: float(_to_decimal_safe(x) / scaling)
                        ),
                        "投資CF": monthly_df["investing"].apply(
                            lambda x: float(_to_decimal_safe(x) / scaling)
                        ),
                        "財務CF": monthly_df["financing"].apply(
                            lambda x: float(_to_decimal_safe(x) / scaling)
                        ),
                        "利息支払": monthly_df["interest"].apply(
                            lambda x: float(_to_decimal_safe(x) / scaling)
                        ),
                        "元本返済": monthly_df["principal"].apply(
                            lambda x: float(_to_decimal_safe(x) / scaling)
                        ),
                        "純増減": monthly_df["net"].apply(
                            lambda x: float(_to_decimal_safe(x) / scaling)
                        ),
                        "累積残高": monthly_df["cumulative"].apply(
                            lambda x: float(_to_decimal_safe(x) / scaling)
                        ),
                    }
                )
                preview_horizon = min(24, len(display_df))
                display_subset = display_df.iloc[:preview_horizon]
                st.dataframe(
                    display_subset,
                    hide_index=True,
                    **use_container_width_kwargs(st.dataframe),
                    column_config={
                        "年": st.column_config.NumberColumn("年", format="%d"),
                        "月": st.column_config.NumberColumn("月", format="%d"),
                        "営業CF": st.column_config.NumberColumn("営業CF", format="%.1f"),
                        "投資CF": st.column_config.NumberColumn("投資CF", format="%.1f"),
                        "財務CF": st.column_config.NumberColumn("財務CF", format="%.1f"),
                        "利息支払": st.column_config.NumberColumn("利息支払", format="%.1f"),
                        "元本返済": st.column_config.NumberColumn("元本返済", format="%.1f"),
                        "純増減": st.column_config.NumberColumn("純増減", format="%.1f"),
                        "累積残高": st.column_config.NumberColumn("累積残高", format="%.1f"),
                    },
                )
                if len(display_df) > preview_horizon:
                    st.caption("※ 25ヶ月目以降はAnalysisタブの詳細資金繰りで確認できます。")

                cumulative_decimals = monthly_df["cumulative"].apply(_to_decimal_safe)
                min_cumulative = cumulative_decimals.min()
                min_index = int(cumulative_decimals.idxmin())
                short_year = int(_to_decimal_safe(monthly_df.loc[min_index, "year"]))
                short_month = int(_to_decimal_safe(monthly_df.loc[min_index, "month"]))
                if min_cumulative < Decimal("0"):
                    st.error(
                        f"FY{short_year} 月{short_month:02d}に{format_amount_with_unit(min_cumulative, unit)}まで現金が減少し資金ショートが想定されます。追加調達やコスト見直しを検討してください。"
                    )
                elif min_cumulative == Decimal("0"):
                    st.warning(
                        f"FY{short_year} 月{short_month:02d}に累積残高がゼロとなります。安全余裕資金の確保を検討してください。"
                    )
                else:
                    st.success("シミュレーション上、累積キャッシュは全期間でプラスを維持しています。")
                st.caption(f"金額は{unit}単位で表示しています。")
    elif preview_issues:
        st.info("入力内容にエラーがあるため、税額と資金繰りの試算を表示できません。保存前に各ステップで赤枠の項目を修正してください。")

    save_col, _ = st.columns([2, 1])
    with save_col:
        if st.button(
            "入力を検証して保存",
            type="primary",
            **use_container_width_kwargs(st.button),
        ):
            if preview_issues:
                st.session_state["finance_validation_errors"] = preview_issues
                st.toast("入力にエラーがあります。赤枠の項目を修正してください。", icon="✖")
            else:
                st.session_state["finance_validation_errors"] = []
                st.session_state[SALES_TEMPLATE_STATE_KEY] = sales_df
                st.session_state["finance_raw"] = bundle_payload
                if preview_bundle:
                    st.session_state["finance_models"] = {
                        "sales": preview_bundle.sales,
                        "costs": preview_bundle.costs,
                        "capex": preview_bundle.capex,
                        "loans": preview_bundle.loans,
                        "tax": preview_bundle.tax,
                    }
                st.toast("財務データを保存しました。", icon="✔")

    st.divider()
    st.subheader("クラウド保存とバージョン管理")

    if not auth.is_authenticated():
        render_callout(
            icon="▣",
            title="アカウントにログインするとクラウド保存できます",
            body="ヘッダー右上のログインからアカウントを作成し、計画をクラウドに保存してバージョン管理しましょう。",
            tone="caution",
        )
    else:
        plan_summaries = auth.available_plan_summaries()
        save_col, load_col = st.columns(2)
        with save_col:
            st.markdown("#### クラウドに保存")
            plan_name = st.text_input(
                "保存する計画名称",
                value=st.session_state.get("plan_save_name", "メイン計画"),
                key="plan_save_name",
                placeholder="例：政策公庫提出用2025",
            )
            plan_note = st.text_input(
                "バージョンメモ (任意)",
                key="plan_save_note",
                placeholder="例：販促強化シナリオ",
            )
            if st.button("クラウドに保存", key="plan_snapshot_save", type="primary"):
                if not plan_name.strip():
                    st.error("計画名称を入力してください。")
                else:
                    try:
                        payload = _build_snapshot_payload()
                        summary = auth.save_snapshot(
                            plan_name=plan_name.strip(),
                            payload=payload,
                            note=plan_note.strip(),
                            description="inputs_page_snapshot",
                        )
                        st.success(
                            f"{summary.plan_name} をバージョン v{summary.version} として保存しました。",
                            icon="✔",
                        )
                        st.session_state["plan_save_note"] = ""
                    except AuthError as exc:
                        st.error(str(exc))
        with load_col:
            st.markdown("#### 保存済みから復元")
            if not plan_summaries:
                st.info("まだ保存済みの計画がありません。保存するとここから復元できます。")
            else:
                plan_labels = {
                    f"{summary.name} (最新v{summary.latest_version})": summary
                    for summary in plan_summaries
                }
                selected_plan_label = st.selectbox(
                    "計画を選択",
                    list(plan_labels.keys()),
                    key="plan_load_plan",
                )
                selected_plan = plan_labels[selected_plan_label]
                versions = auth.available_versions(selected_plan.plan_id)
                if versions:
                    version_labels = {
                        f"v{ver.version}｜{_format_timestamp(ver.created_at)}｜{ver.note or 'メモなし'}": ver
                        for ver in versions
                    }
                    selected_version_label = st.selectbox(
                        "バージョンを選択",
                        list(version_labels.keys()),
                        key="plan_load_version",
                    )
                    selected_version = version_labels[selected_version_label]
                    if st.button("このバージョンを読み込む", key="plan_snapshot_load"):
                        payload = auth.load_snapshot(
                            plan_id=selected_plan.plan_id,
                            version_id=selected_version.id,
                        )
                        if payload is None:
                            st.error("選択したバージョンを読み込めませんでした。")
                        elif _hydrate_snapshot(payload):
                            st.toast(
                                f"{selected_plan.name} v{selected_version.version} を読み込みました。",
                                icon="✔",
                            )
                            st.experimental_rerun()
                else:
                    st.info("選択した計画にはバージョンがまだありません。")

        if plan_summaries:
            summary_df = pd.DataFrame(
                [
                    {
                        "計画名": summary.name,
                        "最新バージョン": summary.latest_version,
                        "最終更新": _format_timestamp(summary.updated_at),
                    }
                    for summary in plan_summaries
                ]
            )
            st.dataframe(
                summary_df,
                hide_index=True,
                use_container_width=True,
            )

st.session_state[BUSINESS_CONTEXT_KEY] = context_state
st.session_state[MARKETING_STRATEGY_KEY] = marketing_state

current_context_snapshot = {
    key: str(context_state.get(key, "")) for key in BUSINESS_CONTEXT_TEMPLATE
}
previous_context_snapshot = st.session_state.get(BUSINESS_CONTEXT_SNAPSHOT_KEY)
if previous_context_snapshot != current_context_snapshot:
    st.session_state[BUSINESS_CONTEXT_SNAPSHOT_KEY] = current_context_snapshot
    st.session_state[BUSINESS_CONTEXT_LAST_SAVED_KEY] = (
        datetime.now().replace(microsecond=0).isoformat()
    )

marketing_snapshot = json.dumps(
    marketing_state,
    ensure_ascii=False,
    sort_keys=True,
)
previous_marketing_snapshot = st.session_state.get(MARKETING_STRATEGY_SNAPSHOT_KEY)
if previous_marketing_snapshot != marketing_snapshot:
    st.session_state[MARKETING_STRATEGY_SNAPSHOT_KEY] = marketing_snapshot
    st.session_state[BUSINESS_CONTEXT_LAST_SAVED_KEY] = (
        datetime.now().replace(microsecond=0).isoformat()
    )

_render_navigation(step_index)
