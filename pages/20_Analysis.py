"""Analytics page showing KPI dashboard, break-even analysis and cash flow."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Dict, List, Tuple, Mapping

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from pydantic import BaseModel, ValidationError

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
from models import (
    INDUSTRY_TEMPLATES,
    CapexPlan,
    LoanSchedule,
    TaxPolicy,
    DEFAULT_TAX_POLICY,
)
from theme import COLOR_BLIND_COLORS, THEME_COLORS, inject_theme
from ui.components import MetricCard, render_metric_cards
from ui.streamlit_compat import use_container_width_kwargs
from services.marketing_strategy import (
    FOUR_P_KEYS,
    FOUR_P_LABELS,
    SESSION_STATE_KEY as MARKETING_STRATEGY_KEY,
    generate_marketing_recommendations,
    marketing_state_has_content,
)

ITEM_LABELS = {code: label for code, label, _ in ITEMS}

PLOTLY_DOWNLOAD_OPTIONS = {
    "format": "png",
    "height": 600,
    "width": 1000,
    "scale": 2,
}

FINANCIAL_SERIES_STATE_KEY = "financial_timeseries"
BUSINESS_CONTEXT_KEY = "business_context"
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

STRATEGIC_ANALYSIS_KEY = "strategic_analysis"
SWOT_CATEGORIES = ("強み", "弱み", "機会", "脅威")
PEST_DIMENSIONS = ("政治", "経済", "社会", "技術")
PEST_DIRECTIONS = ("機会", "脅威")
SWOT_DISPLAY_COLUMNS = ["分類", "要因", "重要度", "確度", "スコア", "備考"]
PEST_DISPLAY_COLUMNS = ["区分", "要因", "影響方向", "影響度", "確度", "スコア", "備考"]

BSC_STATE_KEY = "balanced_scorecard"
BSC_PERSPECTIVES: List[Dict[str, object]] = [
    {
        "key": "financial",
        "label": "財務",
        "metrics": [
            {
                "key": "revenue",
                "label": "売上高",
                "unit_type": "plan_unit",
                "direction": "higher",
                "precision": 1,
                "allow_negative": False,
                "step": 10.0,
                "description": "年間売上の目標金額。資金繰りに直結する最重要指標です。",
            },
            {
                "key": "operating_margin",
                "label": "営業利益率",
                "unit_type": "percent",
                "direction": "higher",
                "precision": 1,
                "allow_negative": True,
                "description": "営業利益÷売上高。収益性とコスト構造の健全性を測る指標です。",
            },
            {
                "key": "payback_period",
                "label": "資本回収期間",
                "unit_type": "year",
                "direction": "lower",
                "precision": 1,
                "allow_negative": False,
                "description": "投資額をキャッシュフローで回収するまでの年数。短いほど望ましい指標です。",
            },
        ],
    },
    {
        "key": "customer",
        "label": "顧客",
        "metrics": [
            {
                "key": "customer_satisfaction",
                "label": "顧客満足度",
                "unit_type": "score",
                "direction": "higher",
                "precision": 1,
                "allow_negative": False,
                "description": "アンケートやNPSなどで測定する顧客体験スコア。",
            },
            {
                "key": "repeat_rate",
                "label": "リピート率",
                "unit_type": "percent",
                "direction": "higher",
                "precision": 1,
                "allow_negative": False,
                "description": "既存顧客の再購入比率。LTVと売上の安定性に寄与します。",
            },
            {
                "key": "churn_rate",
                "label": "解約率",
                "unit_type": "percent",
                "direction": "lower",
                "precision": 1,
                "allow_negative": False,
                "description": "契約顧客の離脱割合。サブスクやリカーリングビジネスで重要です。",
            },
        ],
    },
    {
        "key": "process",
        "label": "業務プロセス",
        "metrics": [
            {
                "key": "lead_time",
                "label": "生産リードタイム",
                "unit_type": "days",
                "direction": "lower",
                "precision": 1,
                "allow_negative": False,
                "description": "受注から納品までの平均日数。短縮で在庫と顧客満足に貢献します。",
            },
            {
                "key": "defect_rate",
                "label": "不良率",
                "unit_type": "percent",
                "direction": "lower",
                "precision": 2,
                "allow_negative": False,
                "description": "生産品に占める不良品の割合。品質管理の指標です。",
            },
            {
                "key": "inventory_turnover",
                "label": "在庫回転率",
                "unit_type": "times",
                "direction": "higher",
                "precision": 1,
                "allow_negative": False,
                "description": "年間の在庫回転回数。高いほど在庫効率が良いことを示します。",
            },
        ],
    },
    {
        "key": "learning",
        "label": "学習と成長",
        "metrics": [
            {
                "key": "training_hours",
                "label": "従業員の教育時間",
                "unit_type": "hours",
                "direction": "higher",
                "precision": 1,
                "allow_negative": False,
                "description": "年間の平均研修時間。スキル醸成と能力開発の指標です。",
            },
            {
                "key": "employee_satisfaction",
                "label": "従業員満足度",
                "unit_type": "score",
                "direction": "higher",
                "precision": 1,
                "allow_negative": False,
                "description": "従業員エンゲージメントやES調査のスコア。",
            },
            {
                "key": "ideas_submitted",
                "label": "提案件数",
                "unit_type": "count",
                "direction": "higher",
                "precision": 0,
                "allow_negative": False,
                "description": "業務改善や新規提案の件数。現場からの学習フィードバックを表します。",
            },
        ],
    },
]

BSC_METRIC_LOOKUP: Dict[str, Dict[str, object]] = {
    metric["key"]: metric
    for perspective in BSC_PERSPECTIVES
    for metric in perspective["metrics"]
}

BSC_SUGGESTION_LIBRARY: Dict[str, List[Dict[str, str]]] = {
    "revenue": [
        {
            "cause": "新規顧客開拓数が不足している",
            "action": "デジタル広告投資の増加や紹介キャンペーンでリード獲得を強化する",
        },
        {
            "cause": "販売チャネルの稼働率が低く受注率が伸びない",
            "action": "営業プロセスを再設計し、提案ストーリーや価格条件の最適化を図る",
        },
    ],
    "operating_margin": [
        {
            "cause": "原価や販管費のコントロールが甘く利益率を圧迫している",
            "action": "主要コストドライバーを特定し、調達交渉や自動化投資で費用構造を是正する",
        },
        {
            "cause": "高粗利の商材構成比が低い",
            "action": "商品ミックスを見直し、ハイマージン商材の販売インセンティブを強化する",
        },
    ],
    "payback_period": [
        {
            "cause": "初期投資が大きくキャッシュ創出が追いついていない",
            "action": "投資効果の早い案件を優先し、スモールスタートで段階的に投資を進める",
        },
        {
            "cause": "営業キャッシュフローが想定より低調",
            "action": "価格改定やアップセル施策でキャッシュインを前倒しし、回収速度を高める",
        },
    ],
    "customer_satisfaction": [
        {
            "cause": "サポート品質や導入後フォローが不足",
            "action": "カスタマーサクセス体制を整備し、オンボーディングプログラムを強化する",
        },
        {
            "cause": "製品UI/UXがニーズに合致していない",
            "action": "顧客インタビューを通じた改善サイクルを高速化し、ロードマップに反映する",
        },
    ],
    "repeat_rate": [
        {
            "cause": "定期購入プランやクロスセルの設計が弱い",
            "action": "リピート特典やサブスクプランを導入し、利用頻度を高める",
        },
        {
            "cause": "顧客接点でのパーソナライズが不足",
            "action": "CRMデータを活用したセグメント別コミュニケーションで再購買を促す",
        },
    ],
    "churn_rate": [
        {
            "cause": "定期顧客の離反率が高い",
            "action": "ロイヤリティプログラムや定期フォローの仕組みを導入し、解約防止を図る",
        },
        {
            "cause": "トラブル時の対応が遅く満足度が低下している",
            "action": "サポート要員を増員し、FAQやセルフサービス導線を整備する",
        },
    ],
    "lead_time": [
        {
            "cause": "工程間のリードタイムが長くボトルネックが発生",
            "action": "工程別のタクトタイムを可視化し、ボトルネック工程への人員再配置を行う",
        },
        {
            "cause": "在庫補充計画が最適化されていない",
            "action": "需要予測と連動したMRPを導入し、段取り替え回数を削減する",
        },
    ],
    "defect_rate": [
        {
            "cause": "標準作業が徹底されておらず品質ばらつきが大きい",
            "action": "QCサークルやポカヨケなどの品質管理手法を導入し、検査工程を自動化する",
        },
        {
            "cause": "仕入先品質に起因する不良が多い",
            "action": "サプライヤー評価を実施し、協働による品質改善プロジェクトを立ち上げる",
        },
    ],
    "inventory_turnover": [
        {
            "cause": "需要予測の精度が低く在庫が過剰",
            "action": "需要シグナルをリアルタイムで取得し、在庫補充の自動化と安全在庫の見直しを行う",
        },
        {
            "cause": "滞留在庫の整理が進んでいない",
            "action": "ABC分析で重点SKUを特定し、廃番や値引き販売で在庫を圧縮する",
        },
    ],
    "training_hours": [
        {
            "cause": "計画的な研修プログラムが不足",
            "action": "年間育成ロードマップを策定し、eラーニングと集合研修を組み合わせる",
        },
        {
            "cause": "現場が多忙で学習時間を確保できない",
            "action": "業務の自動化やシフト再設計で学習時間を確保し、学習KPIを評価制度に連動させる",
        },
    ],
    "employee_satisfaction": [
        {
            "cause": "評価・報酬への納得感が低い",
            "action": "1on1やフィードバックサイクルを整備し、評価基準を透明化する",
        },
        {
            "cause": "ワークライフバランスが悪化",
            "action": "柔軟な働き方の導入や業務プロセス改善で残業時間を削減する",
        },
    ],
    "ideas_submitted": [
        {
            "cause": "改善提案のインセンティブが弱く声が上がらない",
            "action": "表彰制度や小さな改善を称える仕組みを導入し、提案文化を醸成する",
        },
        {
            "cause": "アイデアを具現化する支援が不足",
            "action": "ハッカソンや実験予算を設け、プロトタイピング支援で実行まで伴走する",
        },
    ],
}


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if np.isnan(number) or np.isinf(number):
        return default
    return number


def _ensure_bsc_state() -> Dict[str, Dict[str, Dict[str, float]]]:
    state_raw = st.session_state.get(BSC_STATE_KEY, {})
    if not isinstance(state_raw, dict):
        state_raw = {}
    for perspective in BSC_PERSPECTIVES:
        perspective_key = str(perspective.get("key", ""))
        metrics_state = state_raw.get(perspective_key)
        if not isinstance(metrics_state, dict):
            metrics_state = {}
        for metric in perspective.get("metrics", []):
            metric_key = str(metric.get("key", ""))
            metric_state = metrics_state.get(metric_key)
            if not isinstance(metric_state, dict):
                metric_state = {}
            target = _to_float(metric_state.get("target", 0.0), 0.0)
            actual = _to_float(metric_state.get("actual", 0.0), 0.0)
            metrics_state[metric_key] = {"target": target, "actual": actual}
        state_raw[perspective_key] = metrics_state
    st.session_state[BSC_STATE_KEY] = state_raw
    return state_raw


def _bsc_precision(metric_cfg: Mapping[str, object]) -> int:
    try:
        precision = int(metric_cfg.get("precision", 1))
    except (TypeError, ValueError):
        return 1
    return max(0, precision)


def _bsc_step(metric_cfg: Mapping[str, object]) -> float:
    step_value = metric_cfg.get("step")
    if isinstance(step_value, (int, float)) and not isinstance(step_value, bool):
        return float(step_value)
    precision = _bsc_precision(metric_cfg)
    if precision == 0:
        return 1.0
    return float(round(10 ** (-precision), precision))


def _bsc_unit_label(metric_cfg: Mapping[str, object], plan_unit: str) -> str:
    unit_type = str(metric_cfg.get("unit_type", ""))
    mapping = {
        "percent": "%",
        "hours": "時間",
        "days": "日",
        "times": "回",
        "count": "件",
        "score": "点",
        "year": "年",
    }
    if unit_type == "plan_unit":
        return plan_unit
    return mapping.get(unit_type, "")


def _format_bsc_number(metric_cfg: Mapping[str, object], value: float, plan_unit: str) -> str:
    precision = _bsc_precision(metric_cfg)
    unit_type = str(metric_cfg.get("unit_type", ""))
    if unit_type == "percent":
        return f"{value:.{precision}f}%"
    number_text = (
        f"{value:,.{precision}f}"
        if precision > 0
        else f"{value:,.0f}"
    )
    unit_label = _bsc_unit_label(metric_cfg, plan_unit)
    if unit_label:
        return f"{number_text}{unit_label}"
    return number_text


def _compute_bsc_progress(actual: float, target: float, direction: str) -> float | None:
    if direction == "higher":
        if target <= 0:
            return None
        return actual / target
    if direction == "lower":
        if target <= 0:
            return 1.0 if actual <= target else 0.0
        if actual <= target:
            return 1.0
        if actual <= 0:
            return None
        return target / actual
    return None


def _strategic_records_from_state(key: str) -> List[Dict[str, object]]:
    state = st.session_state.get(STRATEGIC_ANALYSIS_KEY, {})
    if isinstance(state, Mapping):
        data = state.get(key)
        if isinstance(data, list):
            return [record for record in data if isinstance(record, dict)]
    return []


def _bounded_score(value: object, default: float = 3.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(number):
        return default
    return float(min(5.0, max(1.0, number)))


def _swot_dataframe(records: List[Dict[str, object]]) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for record in records:
        category = str(record.get("category", ""))
        if category not in SWOT_CATEGORIES:
            continue
        factor = str(record.get("factor", "")).strip()
        if not factor:
            continue
        impact = _bounded_score(record.get("impact", 3.0))
        probability = _bounded_score(record.get("probability", 3.0))
        note = str(record.get("note", "")).strip()
        score = impact * probability
        rows.append(
            {
                "分類": category,
                "要因": factor,
                "重要度": impact,
                "確度": probability,
                "スコア": score,
                "備考": note,
            }
        )
    if not rows:
        return pd.DataFrame(columns=SWOT_DISPLAY_COLUMNS)
    df = pd.DataFrame(rows)
    for column in SWOT_DISPLAY_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    return df[SWOT_DISPLAY_COLUMNS].copy()


def _pest_dataframe(records: List[Dict[str, object]]) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for record in records:
        dimension = str(record.get("dimension", ""))
        if dimension not in PEST_DIMENSIONS:
            continue
        direction = str(record.get("direction", ""))
        if direction not in PEST_DIRECTIONS:
            continue
        factor = str(record.get("factor", "")).strip()
        if not factor:
            continue
        impact = _bounded_score(record.get("impact", 3.0))
        probability = _bounded_score(record.get("probability", 3.0))
        note = str(record.get("note", "")).strip()
        score = impact * probability
        rows.append(
            {
                "区分": dimension,
                "要因": factor,
                "影響方向": direction,
                "影響度": impact,
                "確度": probability,
                "スコア": score,
                "備考": note,
            }
        )
    if not rows:
        return pd.DataFrame(columns=PEST_DISPLAY_COLUMNS)
    df = pd.DataFrame(rows)
    for column in PEST_DISPLAY_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    return df[PEST_DISPLAY_COLUMNS].copy()


def _swot_summary_table(swot_df: pd.DataFrame) -> pd.DataFrame:
    if swot_df.empty:
        return pd.DataFrame(columns=["分類", "件数", "平均重要度", "平均確度", "平均スコア", "合計スコア"])

    summary_rows: List[Dict[str, object]] = []
    for category in SWOT_CATEGORIES:
        subset = swot_df[swot_df["分類"] == category]
        if subset.empty:
            continue
        summary_rows.append(
            {
                "分類": category,
                "件数": int(len(subset)),
                "平均重要度": round(float(subset["重要度"].mean()), 2),
                "平均確度": round(float(subset["確度"].mean()), 2),
                "平均スコア": round(float(subset["スコア"].mean()), 2),
                "合計スコア": round(float(subset["スコア"].sum()), 2),
            }
        )
    return pd.DataFrame(summary_rows)


def _pest_summary_table(pest_df: pd.DataFrame) -> pd.DataFrame:
    if pest_df.empty:
        return pd.DataFrame(columns=["区分", "影響方向", "件数", "平均影響度", "平均確度", "平均スコア", "合計スコア"])

    grouped = (
        pest_df.groupby(["区分", "影響方向"], dropna=False)
        .agg(
            件数=("要因", "count"),
            平均影響度=("影響度", "mean"),
            平均確度=("確度", "mean"),
            平均スコア=("スコア", "mean"),
            合計スコア=("スコア", "sum"),
        )
        .reset_index()
    )
    for column in ["平均影響度", "平均確度", "平均スコア", "合計スコア"]:
        grouped[column] = grouped[column].astype(float).round(2)
    return grouped


def _swot_quadrant_markdown(swot_df: pd.DataFrame, category: str) -> str:
    subset = swot_df[swot_df["分類"] == category].sort_values("スコア", ascending=False)
    if subset.empty:
        return "- (未入力)"
    lines: List[str] = []
    for _, row in subset.iterrows():
        note = str(row.get("備考", "")).strip()
        note_text = f" ｜ {note}" if note else ""
        lines.append(
            "- {factor}｜スコア {score:.1f}（重要度 {impact:.1f} × 確度 {prob:.1f}）{note}".format(
                factor=str(row["要因"]),
                score=float(row["スコア"]),
                impact=float(row["重要度"]),
                prob=float(row["確度"]),
                note=note_text,
            )
        )
    return "\n".join(lines)


def _top_swot_item(swot_df: pd.DataFrame, category: str) -> Dict[str, object] | None:
    subset = swot_df[swot_df["分類"] == category]
    if subset.empty:
        return None
    best = subset.sort_values(["スコア", "重要度"], ascending=False).iloc[0]
    return {
        "factor": str(best["要因"]),
        "score": float(best["スコア"]),
        "impact": float(best["重要度"]),
        "probability": float(best["確度"]),
    }


def _top_pest_item(pest_df: pd.DataFrame, direction: str) -> Dict[str, object] | None:
    subset = pest_df[pest_df["影響方向"] == direction]
    if subset.empty:
        return None
    best = subset.sort_values(["スコア", "影響度"], ascending=False).iloc[0]
    return {
        "factor": str(best["要因"]),
        "dimension": str(best["区分"]),
        "score": float(best["スコア"]),
        "impact": float(best["影響度"]),
        "probability": float(best["確度"]),
    }


def _safe_decimal(value: object) -> Decimal:
    if value in (None, "", "NaN", "nan"):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _ratio_from_input(value: object) -> Decimal:
    ratio = _safe_decimal(value)
    if ratio.is_nan() or ratio.is_infinite():
        return Decimal("0")
    if ratio > Decimal("1") or ratio < Decimal("-1"):
        ratio = ratio / Decimal("100")
    return ratio


def _financial_series_from_state(fiscal_year: int) -> pd.DataFrame:
    state = st.session_state.get(FINANCIAL_SERIES_STATE_KEY, {})
    records = state.get("records") if isinstance(state, dict) else None
    if not isinstance(records, list) or not records:
        return pd.DataFrame(columns=FINANCIAL_SERIES_COLUMNS)

    df = pd.DataFrame(records).copy()
    if "年度" not in df.columns:
        return pd.DataFrame(columns=FINANCIAL_SERIES_COLUMNS)
    df["年度"] = pd.to_numeric(df["年度"], errors="coerce").fillna(fiscal_year).astype(int)
    if "区分" not in df.columns:
        df["区分"] = ["実績" if year <= fiscal_year - 1 else "計画" for year in df["年度"]]
    else:
        df["区分"] = [
            str(label).strip() if str(label).strip() else ("実績" if year <= fiscal_year - 1 else "計画")
            for label, year in zip(df["区分"], df["年度"])
        ]

    for column in FINANCIAL_SERIES_COLUMNS:
        if column not in df.columns:
            df[column] = 0.0 if column != "区分" else "実績"

    numeric_columns = [col for col in FINANCIAL_SERIES_COLUMNS if col not in ("年度", "区分")]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)

    df["_category_order"] = df["区分"].apply(lambda x: 0 if str(x).strip() == "実績" else 1)
    df = (
        df[FINANCIAL_SERIES_COLUMNS + ["_category_order"]]
        .sort_values(["年度", "_category_order"])
        .drop(columns="_category_order")
        .reset_index(drop=True)
    )
    return df


def _is_finite_decimal(value: Decimal) -> bool:
    return isinstance(value, Decimal) and value.is_finite()


def _compute_financial_metrics_table(
    df: pd.DataFrame, tax_policy: TaxPolicy, fiscal_year: int
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    rows: List[Dict[str, object]] = []
    tax_rate = (
        (tax_policy.corporate_tax_rate or Decimal("0"))
        + (tax_policy.business_tax_rate or Decimal("0"))
    )
    tax_rate = max(Decimal("0"), tax_rate)

    for _, record in df.iterrows():
        year = int(record.get("年度", fiscal_year))
        category_raw = str(record.get("区分", "")).strip()
        category = category_raw if category_raw else ("実績" if year <= fiscal_year - 1 else "計画")

        sales = _safe_decimal(record.get("売上高", 0))
        gross_margin = _ratio_from_input(record.get("粗利益率", 0))
        op_margin = _ratio_from_input(record.get("営業利益率", 0))
        fixed_cost = _safe_decimal(record.get("固定費", 0))
        variable_cost = _safe_decimal(record.get("変動費", 0))
        capex = _safe_decimal(record.get("設備投資額", 0))
        loan_balance = _safe_decimal(record.get("借入残高", 0))
        depreciation = _safe_decimal(record.get("減価償却費", 0))
        total_assets = _safe_decimal(record.get("総資産", 0))

        gross_profit = sales * gross_margin
        operating_profit = sales * op_margin

        if (fixed_cost <= 0) and _is_finite_decimal(gross_profit) and _is_finite_decimal(operating_profit):
            fixed_cost = max(Decimal("0"), gross_profit - operating_profit)

        if variable_cost <= 0 and sales > 0:
            variable_cost = max(Decimal("0"), sales - gross_profit)

        contribution_ratio = gross_margin if gross_margin > 0 else Decimal("0")
        if contribution_ratio <= 0 and sales > 0:
            contribution_ratio = Decimal("1") - (variable_cost / sales)

        if contribution_ratio > 0:
            breakeven_sales = fixed_cost / contribution_ratio
        else:
            breakeven_sales = Decimal("NaN")

        taxes = operating_profit * tax_rate if operating_profit > 0 else Decimal("0")
        ebitda = operating_profit + depreciation
        fcf = operating_profit - taxes + depreciation - capex
        roa = operating_profit / total_assets if total_assets > 0 else Decimal("NaN")
        variable_ratio = variable_cost / sales if sales > 0 else Decimal("NaN")

        rows.append(
            {
                "年度": year,
                "区分": category,
                "売上高": sales,
                "粗利益率": gross_margin,
                "営業利益率": op_margin,
                "固定費": fixed_cost,
                "変動費": variable_cost,
                "設備投資額": capex,
                "借入残高": loan_balance,
                "減価償却費": depreciation,
                "総資産": total_assets,
                "粗利益": gross_profit,
                "営業利益": operating_profit,
                "損益分岐点売上高": breakeven_sales,
                "変動費率": variable_ratio,
                "EBITDA": ebitda,
                "FCF": fcf,
                "ROA": roa,
                "税金": taxes,
            }
        )

    metrics_df = pd.DataFrame(rows)
    metrics_df = metrics_df.sort_values(["年度", "区分"]).reset_index(drop=True)
    return metrics_df


def _monthly_financial_timeseries(metrics_df: pd.DataFrame) -> pd.DataFrame:
    if metrics_df.empty:
        return pd.DataFrame()

    monthly_rows: List[Dict[str, object]] = []
    for _, row in metrics_df.iterrows():
        year = int(row.get("年度", 0))
        sales = row.get("売上高", Decimal("0"))
        breakeven = row.get("損益分岐点売上高", Decimal("NaN"))
        ebitda = row.get("EBITDA", Decimal("0"))
        fcf = row.get("FCF", Decimal("0"))
        loan_balance = row.get("借入残高", Decimal("0"))

        for month in range(1, 13):
            monthly_rows.append(
                {
                    "年度": year,
                    "月": month,
                    "年月": f"FY{year} M{month:02d}",
                    "売上高": sales / Decimal("12") if _is_finite_decimal(sales) else Decimal("NaN"),
                    "損益分岐点売上高": breakeven / Decimal("12") if _is_finite_decimal(breakeven) else Decimal("NaN"),
                    "EBITDA": ebitda / Decimal("12") if _is_finite_decimal(ebitda) else Decimal("NaN"),
                    "FCF": fcf / Decimal("12") if _is_finite_decimal(fcf) else Decimal("NaN"),
                    "借入残高": loan_balance if _is_finite_decimal(loan_balance) else Decimal("NaN"),
                }
            )

    return pd.DataFrame(monthly_rows)


def _decimal_to_float(value: object, divisor: Decimal) -> float | None:
    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not isinstance(decimal_value, Decimal) or not decimal_value.is_finite():
        return None
    divisor = divisor if divisor else Decimal("1")
    return float(decimal_value / divisor)


def _compute_trend_summary(metrics_df: pd.DataFrame) -> Dict[str, float]:
    if metrics_df.empty or len(metrics_df) < 2:
        return {}

    sorted_df = metrics_df.sort_values("年度")
    years = sorted_df["年度"].astype(float).to_numpy()

    def _valid_series(series: pd.Series, transform=None) -> Tuple[np.ndarray, np.ndarray]:
        values = []
        x_values = []
        for year, value in zip(years, series):
            if isinstance(value, Decimal) and value.is_finite():
                numeric_value = float(transform(value) if transform else value)
                values.append(numeric_value)
                x_values.append(year)
        return np.array(x_values, dtype=float), np.array(values, dtype=float)

    summary: Dict[str, float] = {}

    x_sales, sales_values = _valid_series(sorted_df["売上高"])
    if len(x_sales) >= 2:
        slope, _ = np.polyfit(x_sales, sales_values, 1)
        mean_sales = sales_values.mean()
        summary["sales_slope"] = slope
        if mean_sales != 0:
            summary["sales_trend_pct"] = slope / mean_sales
        first = sales_values[0]
        last = sales_values[-1]
        year_span = x_sales[-1] - x_sales[0]
        if first > 0 and year_span > 0:
            summary["sales_cagr"] = (last / first) ** (1 / year_span) - 1

    x_margin, margin_values = _valid_series(
        sorted_df["営業利益率"], transform=lambda v: v * Decimal("100")
    )
    if len(x_margin) >= 2:
        slope_margin, _ = np.polyfit(x_margin, margin_values, 1)
        summary["op_margin_slope"] = slope_margin

    x_roa, roa_values = _valid_series(sorted_df["ROA"], transform=lambda v: v * Decimal("100"))
    if len(x_roa) >= 2:
        slope_roa, _ = np.polyfit(x_roa, roa_values, 1)
        summary["roa_slope"] = slope_roa

    return summary


def _series_total(series: pd.Series) -> float:
    total = 0.0
    for value in series:
        if isinstance(value, Decimal):
            if value.is_finite():
                total += float(value)
        else:
            try:
                total += float(value)
            except (TypeError, ValueError):
                continue
    return total

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


def _coerce_capex_plan(value: object) -> CapexPlan | None:
    if isinstance(value, CapexPlan):
        return value
    if isinstance(value, BaseModel):
        try:
            return CapexPlan.model_validate(value)
        except (ValidationError, TypeError, ValueError):
            return None
    if isinstance(value, Mapping):
        try:
            return CapexPlan.model_validate(dict(value))
        except (ValidationError, TypeError, ValueError):
            return None
    return None


def _coerce_loan_schedule(value: object) -> LoanSchedule | None:
    if isinstance(value, LoanSchedule):
        return value
    if isinstance(value, BaseModel):
        try:
            return LoanSchedule.model_validate(value)
        except (ValidationError, TypeError, ValueError):
            return None
    if isinstance(value, Mapping):
        try:
            return LoanSchedule.model_validate(dict(value))
        except (ValidationError, TypeError, ValueError):
            return None
    return None


def _coerce_tax_policy(value: object) -> TaxPolicy | None:
    if isinstance(value, TaxPolicy):
        return value
    if isinstance(value, BaseModel):
        try:
            return TaxPolicy.model_validate(value)
        except (ValidationError, TypeError, ValueError):
            return None
    if isinstance(value, Mapping):
        try:
            return TaxPolicy.model_validate(dict(value))
        except (ValidationError, TypeError, ValueError):
            return None
    return None


def _monthly_capex_schedule(capex: object) -> Dict[int, Decimal]:
    schedule = {month: Decimal("0") for month in range(1, 13)}
    capex_plan = _coerce_capex_plan(capex)
    if capex_plan is None:
        return schedule
    for entry in capex_plan.payment_schedule():
        if entry.absolute_month <= 12:
            schedule[entry.absolute_month] += entry.amount
    return schedule


def _monthly_debt_schedule(loans: object) -> Dict[int, Dict[str, Decimal]]:
    schedule: Dict[int, Dict[str, Decimal]] = {}
    loan_schedule = _coerce_loan_schedule(loans)
    if loan_schedule is None:
        return schedule
    for entry in loan_schedule.amortization_schedule():
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
    business_rate = _to_decimal(tax_data.get("business_tax_rate", "0"))
    total_rate = corporate_rate + business_rate
    taxes = ebit * total_rate if ebit > 0 else Decimal("0")
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
tax_policy = _coerce_tax_policy(bundle.tax)
if tax_policy is None:
    tax_policy = DEFAULT_TAX_POLICY.model_copy(deep=True)
if not has_custom_inputs:
    st.info("Inputsページでデータを保存すると、分析結果が更新されます。以下は既定値サンプルです。")

plan_cfg = plan_from_models(
    bundle.sales,
    bundle.costs,
    bundle.capex,
    bundle.loans,
    tax_policy,
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
    tax_policy,
    working_capital=working_capital_profile,
)
cf_data = generate_cash_flow(amounts, bundle.capex, bundle.loans, tax_policy)
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
tax_dump = tax_policy.model_dump(mode="json")

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
monthly_cf_entries: List[Dict[str, Decimal]] = []
running_cash = Decimal("0")
for idx, row in monthly_pl_df.iterrows():
    month_index = idx + 1
    operating_profit = Decimal(str(row["営業利益"]))
    interest_month = interest_schedule.get(month_index, Decimal("0"))
    monthly_noe = monthly_other_noe + interest_month
    ordinary_income_month = operating_profit + monthly_noi - monthly_noe
    tax_components_month = tax_policy.income_tax_components(ordinary_income_month)
    taxes_month = tax_components_month["total"]
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

kpi_tab, be_tab, cash_tab, trend_tab, strategy_tab = st.tabs(
    ["KPIダッシュボード", "損益分岐点", "資金繰り", "財務トレンド分析", "SWOT・PEST分析"]
)

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

    st.markdown("### バランス・スコアカード")
    st.caption(
        "財務・顧客・業務プロセス・学習と成長の4視点で目標と実績を入力し、達成度をレーダーと進捗バーで確認します。"
    )
    bsc_state = _ensure_bsc_state()
    perspective_results: List[Dict[str, object]] = []
    improvement_entries: List[Dict[str, object]] = []
    has_input = False

    for perspective in BSC_PERSPECTIVES:
        perspective_key = str(perspective.get("key", ""))
        perspective_label = str(perspective.get("label", perspective_key))
        metrics_cfg = perspective.get("metrics", [])
        metrics_state = bsc_state.get(perspective_key, {})
        st.markdown(f"#### {perspective_label}視点")
        perspective_progress: List[float] = []

        for metric_cfg in metrics_cfg:
            metric_key = str(metric_cfg.get("key", ""))
            metric_label = str(metric_cfg.get("label", metric_key))
            metric_state = metrics_state.get(metric_key, {})
            target_default = _to_float(metric_state.get("target", 0.0), 0.0)
            actual_default = _to_float(metric_state.get("actual", 0.0), 0.0)
            precision = _bsc_precision(metric_cfg)
            step = _bsc_step(metric_cfg)
            number_format = f"%.{precision}f"
            allow_negative = bool(metric_cfg.get("allow_negative", True))
            min_value = None if allow_negative else 0.0

            row_cols = st.columns((2.4, 1.2, 1.2))
            target_kwargs = {
                "value": float(target_default),
                "step": step,
                "key": f"bsc_{perspective_key}_{metric_key}_target",
                "format": number_format,
            }
            actual_kwargs = {
                "value": float(actual_default),
                "step": step,
                "key": f"bsc_{perspective_key}_{metric_key}_actual",
                "format": number_format,
            }
            if min_value is not None:
                target_kwargs["min_value"] = float(min_value)
                actual_kwargs["min_value"] = float(min_value)

            with row_cols[1]:
                target_value = st.number_input("目標値", **target_kwargs)
            with row_cols[2]:
                actual_value = st.number_input("実績値", **actual_kwargs)

            metrics_state[metric_key] = {"target": target_value, "actual": actual_value}
            is_populated = abs(target_value) > 0 or abs(actual_value) > 0
            if is_populated:
                has_input = True

            direction = str(metric_cfg.get("direction", "higher"))
            progress_raw = _compute_bsc_progress(actual_value, target_value, direction)
            if progress_raw is not None and not np.isfinite(progress_raw):
                progress_raw = None

            formatted_target = _format_bsc_number(metric_cfg, target_value, unit)
            formatted_actual = _format_bsc_number(metric_cfg, actual_value, unit)

            with row_cols[0]:
                unit_label = _bsc_unit_label(metric_cfg, unit)
                label_text = f"**{metric_label}**"
                if unit_label:
                    label_text += f"（{unit_label}）"
                st.markdown(label_text)
                description = str(metric_cfg.get("description", ""))
                if description:
                    st.caption(description)

                if progress_raw is None or not is_populated:
                    st.caption("目標と実績を入力すると達成率を算出します。")
                else:
                    progress_display = max(progress_raw, 0.0)
                    clamped_progress = min(progress_display, 1.0)
                    st.progress(clamped_progress)
                    st.caption(
                        f"達成率 {progress_display * 100:.1f}%｜目標 {formatted_target} / 実績 {formatted_actual}"
                    )

            if progress_raw is not None and is_populated:
                perspective_progress.append(min(max(progress_raw, 0.0), 1.2))
                if progress_raw < 0.999:
                    if direction == "lower":
                        gap_value = actual_value - target_value
                        gap_prefix = "超過"
                    else:
                        gap_value = target_value - actual_value
                        gap_prefix = "不足"
                    gap_text = f"{gap_prefix} {_format_bsc_number(metric_cfg, abs(gap_value), unit)}"
                    improvement_entries.append(
                        {
                            "perspective": perspective_label,
                            "metric": metric_label,
                            "progress_pct": max(progress_raw, 0.0) * 100,
                            "target_text": formatted_target,
                            "actual_text": formatted_actual,
                            "gap_text": gap_text,
                            "suggestions": BSC_SUGGESTION_LIBRARY.get(metric_key, []),
                        }
                    )

        bsc_state[perspective_key] = metrics_state
        if perspective_progress:
            average_progress = sum(perspective_progress) / len(perspective_progress)
        else:
            average_progress = None
        perspective_results.append(
            {
                "label": perspective_label,
                "score": average_progress,
            }
        )

    st.session_state[BSC_STATE_KEY] = bsc_state

    if perspective_results:
        score_cols = st.columns(len(perspective_results))
        for col, result in zip(score_cols, perspective_results):
            score_value = result.get("score")
            if score_value is None:
                col.metric(result.get("label", ""), "—")
            else:
                display_score = max(0.0, min(score_value, 1.2)) * 100
                col.metric(result.get("label", ""), f"{display_score:.1f}%")

    valid_scores = [res.get("score") for res in perspective_results if res.get("score") is not None]
    has_valid_scores = bool(valid_scores)
    if has_input and has_valid_scores:
        radar_theta = [res.get("label", "") for res in perspective_results]
        radar_scores = [
            max(0.0, min(res.get("score", 0.0) or 0.0, 1.2)) for res in perspective_results
        ]
        radar_fig = go.Figure(
            data=[
                go.Scatterpolar(
                    r=radar_scores,
                    theta=radar_theta,
                    fill="toself",
                    name="達成率",
                    line=dict(color=palette[0]),
                    marker=dict(color=palette[0]),
                )
            ]
        )
        radar_fig.update_layout(
            template="plotly_white",
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 1.2],
                    tickvals=[0.0, 0.5, 1.0, 1.2],
                    ticktext=["0%", "50%", "100%", "120%"],
                )
            ),
            showlegend=False,
        )
        st.plotly_chart(
            radar_fig,
            use_container_width=True,
            config=plotly_download_config("balanced_scorecard"),
        )
        st.caption("レーダーチャートは各視点の平均達成率を0〜120%スケールで表示します。")
    elif not has_input:
        st.info("各指標の目標値と実績値を入力すると、達成度と改善示唆がここに表示されます。")

    if has_input:
        if improvement_entries:
            st.markdown("#### KPI未達の原因仮説と改善施策")
            lines: List[str] = []
            for entry in improvement_entries:
                lines.append(
                    "- **{perspective}｜{metric}**: 達成率 {progress:.1f}% （目標 {target} / 実績 {actual}｜{gap})".format(
                        perspective=entry["perspective"],
                        metric=entry["metric"],
                        progress=entry["progress_pct"],
                        target=entry["target_text"],
                        actual=entry["actual_text"],
                        gap=entry["gap_text"],
                    )
                )
                for suggestion in entry.get("suggestions", []):
                    lines.append(
                        f"    - 原因例: {suggestion.get('cause', '')}｜改善策: {suggestion.get('action', '')}"
                    )
            st.markdown("\n".join(lines))
        elif has_valid_scores:
            st.success("入力された指標はすべて目標を達成しています。次の打ち手を検討しましょう。")
        else:
            st.info("目標値が未入力の指標があります。目標と実績を設定すると達成度と改善策を算出できます。")

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
    cf_rows = []
    for key, value in cf_data.items():
        amount: float | None
        if isinstance(value, Decimal):
            amount = float(value)
        elif isinstance(value, (int, float)):
            amount = float(value)
        elif isinstance(value, str):
            try:
                amount = float(Decimal(value))
            except (InvalidOperation, ValueError):
                amount = None
        else:
            amount = None

        if amount is not None:
            cf_rows.append({"区分": key, "金額": amount})
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

with trend_tab:
    st.subheader("財務トレンド分析")
    fiscal_year_int = fiscal_year  # fiscal_year is derived from settings_state earlier
    financial_series_df = _financial_series_from_state(fiscal_year_int)
    if financial_series_df.empty:
        st.info("Inputsページの『税制・保存』ステップで財務指標を入力すると、ここに多年度の分析が表示されます。")
    else:
        metrics_timeseries = _compute_financial_metrics_table(
            financial_series_df, tax_policy, fiscal_year_int
        )
        activity_total = 0.0
        for column in ["売上高", "固定費", "変動費", "設備投資額", "借入残高"]:
            if column in metrics_timeseries.columns:
                activity_total += _series_total(metrics_timeseries[column])
        if metrics_timeseries.empty or activity_total == 0.0:
            st.info("財務指標が未入力のため、分析を表示できません。税制・保存ステップで数値を追加してください。")
        else:
            sorted_metrics = metrics_timeseries.sort_values("年度").reset_index(drop=True)
            latest_row = sorted_metrics.iloc[-1]
            summary_cols = st.columns(4)
            summary_cols[0].metric(
                "最新年度 売上高", format_amount_with_unit(latest_row["売上高"], unit)
            )
            summary_cols[1].metric(
                "最新年度 EBITDA", format_amount_with_unit(latest_row["EBITDA"], unit)
            )
            summary_cols[2].metric(
                "最新年度 FCF", format_amount_with_unit(latest_row["FCF"], unit)
            )
            summary_cols[3].metric(
                "最新年度 ROA", format_ratio(latest_row["ROA"])
            )
            st.caption("EBITDAは営業利益に減価償却費を加算した値、FCFは税引後営業CFからCAPEXを控除した値です。")

            annual_display_rows: List[Dict[str, object]] = []
            for _, row in sorted_metrics.iterrows():
                annual_display_rows.append(
                    {
                        "年度": f"FY{int(row['年度'])}",
                        "区分": row["区分"],
                        "売上高": format_amount_with_unit(row["売上高"], unit),
                        "営業利益": format_amount_with_unit(row["営業利益"], unit),
                        "EBITDA": format_amount_with_unit(row["EBITDA"], unit),
                        "FCF": format_amount_with_unit(row["FCF"], unit),
                        "粗利益率": format_ratio(row["粗利益率"]),
                        "営業利益率": format_ratio(row["営業利益率"]),
                        "ROA": format_ratio(row["ROA"]),
                        "損益分岐点売上高": format_amount_with_unit(
                            row["損益分岐点売上高"], unit
                        ),
                    }
                )
            annual_display_df = pd.DataFrame(annual_display_rows)
            st.dataframe(
                annual_display_df,
                hide_index=True,
                **use_container_width_kwargs(st.dataframe),
            )

            monthly_timeseries_df = _monthly_financial_timeseries(sorted_metrics)
            if not monthly_timeseries_df.empty:
                monthly_plot_df = monthly_timeseries_df.copy()
                monthly_plot_df["売上高"] = monthly_plot_df["売上高"].apply(
                    lambda v: _decimal_to_float(v, unit_factor)
                )
                monthly_plot_df["損益分岐点売上高"] = monthly_plot_df["損益分岐点売上高"].apply(
                    lambda v: _decimal_to_float(v, unit_factor)
                )
                monthly_plot_df["EBITDA"] = monthly_plot_df["EBITDA"].apply(
                    lambda v: _decimal_to_float(v, unit_factor)
                )
                monthly_plot_df["FCF"] = monthly_plot_df["FCF"].apply(
                    lambda v: _decimal_to_float(v, unit_factor)
                )
                monthly_plot_df["借入残高"] = monthly_plot_df["借入残高"].apply(
                    lambda v: _decimal_to_float(v, unit_factor)
                )

                monthly_sales_fig = make_subplots(specs=[[{"secondary_y": True}]])
                monthly_sales_fig.add_trace(
                    go.Scatter(
                        x=monthly_plot_df["年月"],
                        y=monthly_plot_df["売上高"],
                        name=f"売上高（月次換算, {unit})",
                        mode="lines",
                        line=dict(color=palette[0], width=3),
                        hovertemplate="%{x}<br>売上高=%{y:,.2f} {unit}<extra></extra>",
                    ),
                    secondary_y=False,
                )
                monthly_sales_fig.add_trace(
                    go.Scatter(
                        x=monthly_plot_df["年月"],
                        y=monthly_plot_df["損益分岐点売上高"],
                        name=f"損益分岐点（月次換算, {unit})",
                        mode="lines",
                        line=dict(color=palette[1], dash="dash"),
                        hovertemplate="%{x}<br>損益分岐点=%{y:,.2f} {unit}<extra></extra>",
                    ),
                    secondary_y=False,
                )
                monthly_sales_fig.add_trace(
                    go.Scatter(
                        x=monthly_plot_df["年月"],
                        y=monthly_plot_df["借入残高"],
                        name=f"借入残高 ({unit})",
                        mode="lines",
                        line=dict(color=palette[2]),
                        hovertemplate="%{x}<br>借入残高=%{y:,.2f} {unit}<extra></extra>",
                    ),
                    secondary_y=True,
                )
                monthly_sales_fig.update_layout(
                    hovermode="x unified",
                    xaxis=dict(tickangle=-45),
                    yaxis_title=f"金額 ({unit})",
                    yaxis2=dict(title=f"借入残高 ({unit})", overlaying="y", side="right"),
                    legend=dict(title=""),
                )
                st.plotly_chart(
                    monthly_sales_fig,
                    use_container_width=True,
                    config=plotly_download_config("financial_monthly_sales"),
                )

                monthly_cash_fig = go.Figure()
                monthly_cash_fig.add_trace(
                    go.Bar(
                        x=monthly_plot_df["年月"],
                        y=monthly_plot_df["EBITDA"],
                        name=f"EBITDA ({unit})",
                        marker_color=palette[3],
                        hovertemplate="%{x}<br>EBITDA=%{y:,.2f} {unit}<extra></extra>",
                    )
                )
                monthly_cash_fig.add_trace(
                    go.Bar(
                        x=monthly_plot_df["年月"],
                        y=monthly_plot_df["FCF"],
                        name=f"フリーCF ({unit})",
                        marker_color=palette[4],
                        hovertemplate="%{x}<br>フリーCF=%{y:,.2f} {unit}<extra></extra>",
                    )
                )
                monthly_cash_fig.update_layout(
                    barmode="group",
                    xaxis=dict(tickangle=-45),
                    yaxis_title=f"金額 ({unit})",
                    legend=dict(title=""),
                )
                st.plotly_chart(
                    monthly_cash_fig,
                    use_container_width=True,
                    config=plotly_download_config("financial_monthly_cash"),
                )
            else:
                st.info("売上高などの値がゼロのため月次換算グラフを描画できません。数値を入力すると推移が表示されます。")

            ratio_fig = go.Figure()
            gross_ratio_series = [
                float(value * Decimal("100"))
                if isinstance(value, Decimal) and value.is_finite()
                else None
                for value in sorted_metrics["粗利益率"]
            ]
            op_ratio_series = [
                float(value * Decimal("100"))
                if isinstance(value, Decimal) and value.is_finite()
                else None
                for value in sorted_metrics["営業利益率"]
            ]
            roa_ratio_series = [
                float(value * Decimal("100"))
                if isinstance(value, Decimal) and value.is_finite()
                else None
                for value in sorted_metrics["ROA"]
            ]

            ratio_fig.add_trace(
                go.Scatter(
                    x=sorted_metrics["年度"],
                    y=gross_ratio_series,
                    name="粗利益率",
                    mode="lines+markers",
                    line=dict(color=palette[0]),
                    hovertemplate="FY%{x}<br>粗利益率=%{y:.1f}%<extra></extra>",
                )
            )
            ratio_fig.add_trace(
                go.Scatter(
                    x=sorted_metrics["年度"],
                    y=op_ratio_series,
                    name="営業利益率",
                    mode="lines+markers",
                    line=dict(color=palette[1]),
                    hovertemplate="FY%{x}<br>営業利益率=%{y:.1f}%<extra></extra>",
                )
            )
            if any(value is not None for value in roa_ratio_series):
                ratio_fig.add_trace(
                    go.Scatter(
                        x=sorted_metrics["年度"],
                        y=roa_ratio_series,
                        name="ROA",
                        mode="lines+markers",
                        line=dict(color=palette[2]),
                        hovertemplate="FY%{x}<br>ROA=%{y:.1f}%<extra></extra>",
                    )
                )
            ratio_fig.update_layout(
                yaxis_title="割合 (%)",
                hovermode="x unified",
                legend=dict(title=""),
            )
            st.plotly_chart(
                ratio_fig,
                use_container_width=True,
                config=plotly_download_config("financial_ratio_trend"),
            )
            st.caption("粗利率・営業利益率・ROAの年次推移。改善傾向を確認できます。")

            trend_summary = _compute_trend_summary(sorted_metrics)
            if trend_summary:
                st.markdown("#### トレンド指標")
                trend_entries: List[Tuple[str, str, str | None]] = []
                if "sales_trend_pct" in trend_summary and "sales_slope" in trend_summary:
                    slope_amount = Decimal(str(trend_summary["sales_slope"]))
                    trend_entries.append(
                        (
                            "売上回帰トレンド",
                            f"{trend_summary['sales_trend_pct'] * 100:.2f}%/年",
                            f"{format_amount_with_unit(slope_amount, unit)}/年",
                        )
                    )
                if "sales_cagr" in trend_summary:
                    trend_entries.append(
                        (
                            "売上CAGR",
                            f"{trend_summary['sales_cagr'] * 100:.2f}%",
                            None,
                        )
                    )
                if "op_margin_slope" in trend_summary:
                    latest_margin = sorted_metrics["営業利益率"].iloc[-1]
                    if isinstance(latest_margin, Decimal) and latest_margin.is_finite():
                        margin_value = f"{float(latest_margin * Decimal('100')):.1f}%"
                    else:
                        margin_value = "—"
                    trend_entries.append(
                        (
                            "営業利益率トレンド",
                            margin_value,
                            f"{trend_summary['op_margin_slope']:.2f} pt/年",
                        )
                    )
                if "roa_slope" in trend_summary:
                    latest_roa = sorted_metrics["ROA"].iloc[-1]
                    if isinstance(latest_roa, Decimal) and latest_roa.is_finite():
                        roa_value = f"{float(latest_roa * Decimal('100')):.1f}%"
                    else:
                        roa_value = "—"
                    trend_entries.append(
                        (
                            "ROAトレンド",
                            roa_value,
                            f"{trend_summary['roa_slope']:.2f} pt/年",
                        )
                    )

                if trend_entries:
                    trend_cols = st.columns(len(trend_entries))
                    for idx, (label, value, delta) in enumerate(trend_entries):
                        if delta is not None:
                            trend_cols[idx].metric(label, value, delta=delta)
                        else:
                            trend_cols[idx].metric(label, value)
            else:
                st.caption("回帰分析は2期間以上のデータが必要です。")


with strategy_tab:
    st.subheader("マーケティング戦略サマリー")
    marketing_state = st.session_state.get(MARKETING_STRATEGY_KEY, {})
    if not marketing_state_has_content(marketing_state):
        st.info("Inputsページ『ビジネスモデル整理』ステップで4P/3C情報を入力すると、ここに提案が表示されます。")
    else:
        business_context = st.session_state.get(BUSINESS_CONTEXT_KEY, {})
        marketing_summary = generate_marketing_recommendations(marketing_state, business_context)
        st.caption("4P・3C入力をもとに自動生成された強化策とポジショニングの提案です。")

        competitor_highlights = marketing_summary.get("competitor_highlights", [])
        if competitor_highlights:
            st.markdown("**競合比較ハイライト**")
            st.markdown("\n".join(f"- {item}" for item in competitor_highlights))

        four_p_recs = marketing_summary.get("four_p", {})
        suggestion_cols = st.columns(2)
        column_map = {"product": 0, "price": 0, "place": 1, "promotion": 1}
        for key in FOUR_P_KEYS:
            label = FOUR_P_LABELS[key]
            column_index = column_map.get(key, 0)
            with suggestion_cols[column_index]:
                st.markdown(f"**{label}**")
                lines = four_p_recs.get(key, [])
                if lines:
                    st.markdown("\n".join(f"- {line}" for line in lines))
                else:
                    st.markdown("- 提案を生成するにはInputsページで詳細を入力してください。")

        st.markdown("**顧客価値提案 (UVP)**")
        st.write(marketing_summary.get("uvp", ""))

        st.markdown("**STP提案**")
        st.markdown(
            "\n".join(
                [
                    f"- セグメンテーション: {marketing_summary.get('segmentation', '')}",
                    f"- ターゲティング: {marketing_summary.get('targeting', '')}",
                    f"- ポジショニング: {marketing_summary.get('positioning', '')}",
                ]
            )
        )
        positioning_points = marketing_summary.get("positioning_points", [])
        if positioning_points:
            st.markdown("\n".join(f"- {point}" for point in positioning_points))

        competitor_table = marketing_summary.get("competitor_table", [])
        if competitor_table:
            competitor_df = pd.DataFrame(competitor_table)
            st.dataframe(
                competitor_df,
                hide_index=True,
                **use_container_width_kwargs(st.dataframe),
            )

    st.subheader("SWOT・PEST分析")
    swot_records = _strategic_records_from_state("swot")
    pest_records = _strategic_records_from_state("pest")
    swot_df = _swot_dataframe(swot_records)
    pest_df = _pest_dataframe(pest_records)

    if swot_df.empty and pest_df.empty:
        st.info("Inputsページ『ビジネスモデル整理』ステップでSWOT/PESTを入力すると、ここに分析結果が表示されます。")
    else:
        if not swot_df.empty:
            st.markdown("#### SWOTマトリクス")
            top_row = st.columns(2)
            with top_row[0]:
                st.markdown("**強み (Strengths)**")
                st.markdown(_swot_quadrant_markdown(swot_df, "強み"))
            with top_row[1]:
                st.markdown("**弱み (Weaknesses)**")
                st.markdown(_swot_quadrant_markdown(swot_df, "弱み"))
            bottom_row = st.columns(2)
            with bottom_row[0]:
                st.markdown("**機会 (Opportunities)**")
                st.markdown(_swot_quadrant_markdown(swot_df, "機会"))
            with bottom_row[1]:
                st.markdown("**脅威 (Threats)**")
                st.markdown(_swot_quadrant_markdown(swot_df, "脅威"))
            st.caption("スコア = 重要度 × 確度。値が大きいほど優先的に検討すべき要因です。")

            swot_summary = _swot_summary_table(swot_df)
            if not swot_summary.empty:
                st.dataframe(
                    swot_summary,
                    hide_index=True,
                    **use_container_width_kwargs(st.dataframe),
                )
        else:
            st.info("SWOTの入力が未登録のため、マトリクスを表示できません。Inputsページで要因を整理してください。")

        if not pest_df.empty:
            st.markdown("#### PEST分析サマリー")
            pest_summary = _pest_summary_table(pest_df)
            if not pest_summary.empty:
                st.dataframe(
                    pest_summary,
                    hide_index=True,
                    **use_container_width_kwargs(st.dataframe),
                )
            with st.expander("PEST要因の詳細", expanded=False):
                detailed = pest_df.sort_values("スコア", ascending=False).copy()
                for column in ["影響度", "確度", "スコア"]:
                    detailed[column] = detailed[column].astype(float).round(2)
                st.dataframe(
                    detailed,
                    hide_index=True,
                    **use_container_width_kwargs(st.dataframe),
                )
        else:
            st.info("PESTの入力が未登録のため、外部環境サマリーを表示できません。政治・経済などの要因を追記しましょう。")

        st.markdown("#### 戦略インサイト")
        comments: List[str] = []

        strength_subset = swot_df[swot_df["分類"] == "強み"]
        weakness_subset = swot_df[swot_df["分類"] == "弱み"]
        opportunity_subset_swot = swot_df[swot_df["分類"] == "機会"]
        threat_subset_swot = swot_df[swot_df["分類"] == "脅威"]
        opportunity_subset_pest = pest_df[pest_df["影響方向"] == "機会"]
        threat_subset_pest = pest_df[pest_df["影響方向"] == "脅威"]

        strength_count = int(len(strength_subset))
        weakness_count = int(len(weakness_subset))
        opportunity_count = int(len(opportunity_subset_swot) + len(opportunity_subset_pest))
        threat_count = int(len(threat_subset_swot) + len(threat_subset_pest))

        strength_total = float(strength_subset["スコア"].sum())
        weakness_total = float(weakness_subset["スコア"].sum())
        opportunity_total = float(opportunity_subset_swot["スコア"].sum()) + float(
            opportunity_subset_pest["スコア"].sum()
        )
        threat_total = float(threat_subset_swot["スコア"].sum()) + float(threat_subset_pest["スコア"].sum())

        strength_avg = strength_total / strength_count if strength_count else 0.0
        weakness_avg = weakness_total / weakness_count if weakness_count else 0.0
        opportunity_avg = opportunity_total / opportunity_count if opportunity_count else 0.0
        threat_avg = threat_total / threat_count if threat_count else 0.0

        if strength_count and opportunity_count:
            synergy_index = strength_avg * opportunity_avg
            top_strength = _top_swot_item(swot_df, "強み")
            top_opportunity = _top_swot_item(swot_df, "機会")
            opportunity_source = "SWOT"
            if top_opportunity is None:
                top_opportunity = _top_pest_item(pest_df, "機会")
                opportunity_source = "PEST"
            detail_text = ""
            if top_strength and top_opportunity:
                opportunity_label = top_opportunity["factor"]
                if opportunity_source == "PEST" and top_opportunity.get("dimension"):
                    opportunity_label = f"{opportunity_label}（{top_opportunity['dimension']}）"
                detail_text = (
                    f"重点：『{top_strength['factor']}』（スコア{top_strength['score']:.1f}）×『{opportunity_label}』"
                    f"（スコア{top_opportunity['score']:.1f}）"
                )
            comments.append(
                "強み×機会の活用余地指数: {index:.1f}（強み平均スコア {s_avg:.1f} / {s_count}件, "
                "機会平均スコア {o_avg:.1f} / {o_count}件）{detail}".format(
                    index=synergy_index,
                    s_avg=strength_avg,
                    s_count=strength_count,
                    o_avg=opportunity_avg,
                    o_count=opportunity_count,
                    detail=f" — {detail_text}" if detail_text else "",
                )
            )

        if weakness_count and threat_count:
            risk_index = weakness_avg * threat_avg
            top_weakness = _top_swot_item(swot_df, "弱み")
            top_threat = _top_swot_item(swot_df, "脅威")
            threat_source = "SWOT"
            if top_threat is None:
                top_threat = _top_pest_item(pest_df, "脅威")
                threat_source = "PEST"
            detail_text = ""
            if top_weakness and top_threat:
                threat_label = top_threat["factor"]
                if threat_source == "PEST" and top_threat.get("dimension"):
                    threat_label = f"{threat_label}（{top_threat['dimension']}）"
                detail_text = (
                    f"重点対策：『{top_weakness['factor']}』（スコア{top_weakness['score']:.1f}）×『{threat_label}』"
                    f"（スコア{top_threat['score']:.1f}）"
                )
            comments.append(
                "弱み×脅威の回避優先度指数: {index:.1f}（弱み平均スコア {w_avg:.1f} / {w_count}件, "
                "脅威平均スコア {t_avg:.1f} / {t_count}件）{detail}".format(
                    index=risk_index,
                    w_avg=weakness_avg,
                    w_count=weakness_count,
                    t_avg=threat_avg,
                    t_count=threat_count,
                    detail=f" — {detail_text}" if detail_text else "",
                )
            )

        if comments:
            st.markdown("\n".join(f"- {comment}" for comment in comments))
        else:
            st.caption("強み・弱み・機会・脅威の入力が不足しているため、定量コメントを生成できませんでした。")
