"""Scenario planning and sensitivity analysis dashboard."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Tuple

import altair as alt
import itertools
import math
import numpy as np
import pandas as pd
import streamlit as st

from calc import compute, generate_cash_flow, plan_from_models, summarize_plan_metrics
from formatting import format_amount_with_unit, format_delta
from models import CapexPlan, LoanSchedule, TaxPolicy
from state import ensure_session_defaults, load_finance_bundle
from theme import inject_theme
from ui.navigation import render_global_navigation, render_workflow_banner
from ui.streamlit_compat import use_container_width_kwargs

st.set_page_config(
    page_title="経営計画スタジオ｜シナリオ",
    page_icon="∑",
    layout="wide",
)

inject_theme()
ensure_session_defaults()

render_global_navigation("scenarios")
render_workflow_banner("scenarios")

DRIVER_LABELS: Dict[str, str] = {
    "customers": "客数",
    "price": "客単価",
    "cost": "原価率",
    "fixed": "固定費",
}

METRIC_LABELS: Dict[str, str] = {
    "sales": "売上高",
    "gross": "粗利",
    "ebit": "EBIT (営業利益)",
    "ord": "経常利益",
    "fcf": "FCF",
    "dscr": "DSCR",
}

SCENARIO_COLUMNS: List[str] = [
    "key",
    "name",
    "customers_pct",
    "price_pct",
    "cost_pct",
    "fixed_pct",
    "notes",
]

PERCENT_COLUMNS: Tuple[str, ...] = (
    "customers_pct",
    "price_pct",
    "cost_pct",
    "fixed_pct",
)

DEFAULT_SCENARIOS: Dict[str, Dict[str, object]] = {
    "baseline": {
        "name": "Baseline",
        "customers_pct": 0.0,
        "price_pct": 0.0,
        "cost_pct": 0.0,
        "fixed_pct": 0.0,
        "notes": "現状見通し",
    },
    "best": {
        "name": "Best",
        "customers_pct": 8.0,
        "price_pct": 5.0,
        "cost_pct": -4.0,
        "fixed_pct": -2.0,
        "notes": "需要増加と効率化",
    },
    "worst": {
        "name": "Worst",
        "customers_pct": -6.0,
        "price_pct": -3.0,
        "cost_pct": 4.0,
        "fixed_pct": 3.0,
        "notes": "需要減少とコスト上昇",
    },
}

SCENARIO_PRESETS: Dict[str, Dict[str, object]] = {
    **DEFAULT_SCENARIOS,
    "new_product": {
        "name": "新製品投入",
        "customers_pct": 6.0,
        "price_pct": 4.0,
        "cost_pct": 1.5,
        "fixed_pct": 3.0,
        "notes": "マーケ強化と試作コストを想定",
    },
    "cost_reduction": {
        "name": "人件費削減",
        "customers_pct": 0.0,
        "price_pct": 0.0,
        "cost_pct": -2.0,
        "fixed_pct": -5.0,
        "notes": "業務効率化・自動化による固定費圧縮",
    },
    "raw_material_shock": {
        "name": "原材料価格高騰",
        "customers_pct": -2.0,
        "price_pct": 1.0,
        "cost_pct": 6.0,
        "fixed_pct": 0.0,
        "notes": "仕入れコスト上昇を一部価格転嫁",
    },
    "omnichannel_expansion": {
        "name": "EC販路拡大",
        "customers_pct": 10.0,
        "price_pct": -1.5,
        "cost_pct": 2.5,
        "fixed_pct": 4.0,
        "notes": "オンライン販路投資と集客増",
    },
}

DISTRIBUTION_OPTIONS: Dict[str, str] = {
    "normal": "正規分布",
    "triangular": "三角分布",
    "uniform": "一様分布",
}

MAX_MULTI_DRIVERS = 5

DEFAULT_MC_CONFIG: Dict[str, Dict[str, float | str]] = {
    "customers": {"mean_pct": 0.0, "std_pct": 3.0, "distribution": "normal"},
    "price": {"mean_pct": 0.0, "std_pct": 2.0, "distribution": "normal"},
    "cost": {"mean_pct": 0.0, "std_pct": 1.5, "distribution": "normal"},
    "fixed": {"mean_pct": 0.0, "std_pct": 1.0, "distribution": "normal"},
}

FIXED_COST_CODES = ["OPEX_H", "OPEX_AD", "OPEX_UTIL", "OPEX_OTH", "OPEX_DEP"]

COGS_CODES = ["COGS_MAT", "COGS_LBR", "COGS_OUT_SRC", "COGS_OUT_CON", "COGS_OTH"]


def _decimal(value: float | Decimal) -> Decimal:
    """Return *value* as :class:`~decimal.Decimal`."""

    return Decimal(str(value))


def _fraction(value_pct: float | Decimal) -> Decimal:
    """Convert a percentage value into a decimal fraction."""

    return _decimal(value_pct) / Decimal("100")


def _clamp_pct(value: float, *, minimum: float = -100.0, maximum: float = 100.0) -> float:
    """Clamp percentage values to avoid unrealistic outliers."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(number):
        return 0.0
    return max(minimum, min(maximum, number))


def _ensure_editor_state() -> Dict[str, object]:
    """Return the scenario editor state dictionary."""

    editor_state = st.session_state.setdefault("scenario_editor", {})
    if "next_id" not in editor_state:
        editor_state["next_id"] = 1
    return editor_state


def _default_scenario_dataframe() -> pd.DataFrame:
    """Return the default scenario definitions as a dataframe."""

    rows: List[Dict[str, object]] = []
    for key, cfg in DEFAULT_SCENARIOS.items():
        rows.append(
            {
                "key": key,
                "name": cfg.get("name", key.title()),
                "customers_pct": float(cfg.get("customers_pct", 0.0)),
                "price_pct": float(cfg.get("price_pct", 0.0)),
                "cost_pct": float(cfg.get("cost_pct", 0.0)),
                "fixed_pct": float(cfg.get("fixed_pct", 0.0)),
                "notes": str(cfg.get("notes", "")),
            }
        )
    return pd.DataFrame(rows, columns=SCENARIO_COLUMNS)


def _sanitize_scenario_df(df: pd.DataFrame | None) -> pd.DataFrame:
    """Clean the scenario dataframe and ensure required columns exist."""

    editor_state = _ensure_editor_state()
    if df is None or df.empty:
        editor_state.setdefault("next_id", 1)
        return _default_scenario_dataframe()

    cleaned_rows: List[Dict[str, object]] = []
    seen_keys: Dict[str, int] = {}

    for _, row in df.iterrows():
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        record: Dict[str, object] = {
            "name": name,
            "notes": str(row.get("notes", "") or "").strip(),
        }
        key_raw = str(row.get("key", "")).strip()
        if not key_raw or key_raw.lower() == "nan":
            key_raw = f"custom_{editor_state['next_id']}"
            editor_state["next_id"] += 1
        counter = seen_keys.get(key_raw, 0)
        if counter:
            key = f"{key_raw}_{counter+1}"
            seen_keys[key_raw] = counter + 1
        else:
            key = key_raw
            seen_keys[key_raw] = 1
        record["key"] = key
        for pct_col in PERCENT_COLUMNS:
            value = row.get(pct_col, 0.0)
            value = 0.0 if value is None else float(value)
            record[pct_col] = _clamp_pct(value, minimum=-50.0, maximum=50.0)
        cleaned_rows.append(record)

    if not cleaned_rows:
        return _default_scenario_dataframe()

    return pd.DataFrame(cleaned_rows, columns=SCENARIO_COLUMNS)


def _append_preset_scenario(df: pd.DataFrame, preset_key: str) -> pd.DataFrame:
    """Return *df* with a preset scenario appended."""

    preset = SCENARIO_PRESETS.get(preset_key)
    if not preset:
        return df
    editor_state = _ensure_editor_state()
    base_key = preset_key
    existing_keys = set(df["key"].astype(str)) if not df.empty else set()
    if base_key in existing_keys:
        base_key = f"{base_key}_{editor_state['next_id']}"
        editor_state["next_id"] += 1
    record = {
        "key": base_key,
        "name": preset.get("name", preset_key.title()),
        "customers_pct": _clamp_pct(float(preset.get("customers_pct", 0.0)), minimum=-50.0, maximum=50.0),
        "price_pct": _clamp_pct(float(preset.get("price_pct", 0.0)), minimum=-50.0, maximum=50.0),
        "cost_pct": _clamp_pct(float(preset.get("cost_pct", 0.0)), minimum=-50.0, maximum=50.0),
        "fixed_pct": _clamp_pct(float(preset.get("fixed_pct", 0.0)), minimum=-50.0, maximum=50.0),
        "notes": str(preset.get("notes", "")),
    }
    updated = pd.concat([df, pd.DataFrame([record], columns=SCENARIO_COLUMNS)], ignore_index=True)
    return _sanitize_scenario_df(updated)


def _scenario_percent_label(value: float) -> str:
    """Return a formatted percentage label with sign."""

    return f"{value:+.1f}%"


def _scenario_risk_flags(
    result: Dict[str, Decimal],
    *,
    var_limit: float | None,
    dscr_floor: float | None,
) -> str:
    """Return textual risk flags for a scenario evaluation."""

    flags: List[str] = []
    fcf_value = result.get("fcf", Decimal("0"))
    dscr_value = result.get("dscr", Decimal("NaN"))
    if var_limit is not None and fcf_value < Decimal(str(var_limit)):
        flags.append("VaR閾値未達")
    if dscr_floor is not None:
        try:
            if Decimal(dscr_value) < Decimal(str(dscr_floor)):
                flags.append("DSCR下限未達")
        except Exception:
            pass
    return " / ".join(flags) if flags else "—"


def _profit_curve_frame(series: pd.Series | None) -> pd.DataFrame:
    """Return cumulative distribution points for profit curve charts."""

    if series is None:
        return pd.DataFrame({"Metric": [], "累積確率": []})
    cleaned = series.dropna()
    if cleaned.empty:
        return pd.DataFrame({"Metric": [], "累積確率": []})
    sorted_vals = np.sort(cleaned.to_numpy())
    cumulative = np.arange(1, len(sorted_vals) + 1) / len(sorted_vals)
    return pd.DataFrame({"Metric": sorted_vals, "累積確率": cumulative})
def _format_multiple(value: Decimal | float) -> str:
    """Format multiples (e.g. DSCR) with two decimals."""

    try:
        number = Decimal(str(value))
    except Exception:
        return "—"
    if number.is_nan() or number.is_infinite():
        return "—"
    quantized = number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{quantized}倍"


def _compute_fcf(amounts: Dict[str, Decimal], capex: CapexPlan, tax: TaxPolicy) -> Decimal:
    """Calculate free cash flow using EBIT - taxes + depreciation - CAPEX."""

    ebit = Decimal(amounts.get("OP", Decimal("0")))
    depreciation = Decimal(amounts.get("OPEX_DEP", Decimal("0")))
    taxes = tax.effective_tax(Decimal(amounts.get("ORD", Decimal("0"))))
    capex_total = capex.total_investment()
    return ebit - taxes + depreciation - capex_total


def _calculate_dscr(loans: LoanSchedule, operating_cf: Decimal) -> Decimal:
    """Return the first positive DSCR based on annual debt service."""

    if operating_cf <= 0:
        return Decimal("NaN")

    yearly_totals: Dict[int, Dict[str, Decimal]] = {}
    for loan in loans.loans:
        principal = Decimal(loan.principal)
        rate = Decimal(loan.interest_rate)
        term_months = int(loan.term_months)
        start_month = int(loan.start_month)
        repayment_type = str(loan.repayment_type)
        if principal <= 0 or term_months <= 0:
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
            outstanding -= principal_payment
            bucket = yearly_totals.setdefault(
                year_index, {"interest": Decimal("0"), "principal": Decimal("0")}
            )
            bucket["interest"] += interest
            bucket["principal"] += principal_payment

    for year in sorted(yearly_totals.keys()):
        debt_service = yearly_totals[year]["interest"] + yearly_totals[year]["principal"]
        if debt_service > 0:
            return operating_cf / debt_service
    return Decimal("NaN")


def _scenario_amounts(
    plan_cfg: object,
    *,
    customers_change: Decimal,
    price_change: Decimal,
    cost_change: Decimal,
    fixed_change: Decimal,
) -> Dict[str, Decimal]:
    requires_clone = cost_change != Decimal("0") or fixed_change != Decimal("0")
    plan = plan_cfg.clone() if requires_clone else plan_cfg
    if cost_change != 0:
        factor = Decimal("1") + cost_change
        for code in COGS_CODES:
            cfg = plan.items.get(code)
            if not cfg:
                continue
            current_value = Decimal(cfg.get("value", Decimal("0")))
            cfg["value"] = current_value * factor
    if fixed_change != 0:
        factor = Decimal("1") + fixed_change
        for code in FIXED_COST_CODES:
            cfg = plan.items.get(code)
            if not cfg:
                continue
            current_value = Decimal(cfg.get("value", Decimal("0")))
            cfg["value"] = current_value * factor
    sales_factor = (Decimal("1") + customers_change) * (Decimal("1") + price_change)
    sales_override = Decimal(plan.base_sales) * sales_factor
    return compute(plan, sales_override=sales_override)


def evaluate_scenario(
    plan_cfg: object,
    *,
    capex: CapexPlan,
    loans: LoanSchedule,
    tax: TaxPolicy,
    customers_change: Decimal,
    price_change: Decimal,
    cost_change: Decimal,
    fixed_change: Decimal,
) -> Dict[str, Decimal]:
    """Evaluate a scenario and return core metrics."""

    amounts = _scenario_amounts(
        plan_cfg,
        customers_change=customers_change,
        price_change=price_change,
        cost_change=cost_change,
        fixed_change=fixed_change,
    )
    metrics = summarize_plan_metrics(amounts)
    cf_data = generate_cash_flow(amounts, capex, loans, tax)
    operating_cf = Decimal(cf_data.get("営業キャッシュフロー", Decimal("0")))
    result = {
        "sales": Decimal(amounts.get("REV", Decimal("0"))),
        "gross": Decimal(amounts.get("GROSS", Decimal("0"))),
        "ebit": Decimal(amounts.get("OP", Decimal("0"))),
        "ord": Decimal(amounts.get("ORD", Decimal("0"))),
        "fcf": _compute_fcf(amounts, capex, tax),
        "dscr": _calculate_dscr(loans, operating_cf),
        "amounts": amounts,
        "metrics": metrics,
    }
    return result


def _metric_value(result: Dict[str, Decimal], metric_key: str) -> Decimal:
    key_map = {
        "sales": "sales",
        "gross": "gross",
        "ebit": "ebit",
        "ord": "ord",
        "fcf": "fcf",
        "dscr": "dscr",
    }
    mapped = key_map.get(metric_key, "sales")
    value = result.get(mapped, Decimal("0"))
    return Decimal(value)


def serialize_plan_config(plan_cfg: object) -> Dict[str, object]:
    """Serialize :class:`~calc.pl.PlanConfig` for cached Monte Carlo runs."""

    payload: Dict[str, object] = {
        "base_sales": str(plan_cfg.base_sales),
        "fte": str(plan_cfg.fte),
        "unit": plan_cfg.unit,
        "items": {},
    }
    for code, cfg in plan_cfg.items.items():
        payload["items"][code] = {
            "method": cfg.get("method"),
            "value": str(cfg.get("value", "0")),
            "rate_base": str(cfg.get("rate_base", "sales")),
        }
    return payload


def deserialize_plan_config(data: Dict[str, object]) -> object:
    from calc.pl import PlanConfig  # local import to avoid circular deps in Streamlit

    plan = PlanConfig(
        Decimal(str(data.get("base_sales", "0"))),
        Decimal(str(data.get("fte", "0"))),
        str(data.get("unit", "百万円")),
    )
    items = data.get("items", {})
    for code, cfg in items.items():
        method = str(cfg.get("method", "amount"))
        value = Decimal(str(cfg.get("value", "0")))
        rate_base = str(cfg.get("rate_base", "sales"))
        if method == "rate":
            plan.set_rate(code, value, rate_base=rate_base)
        else:
            plan.set_amount(code, value)
    return plan


def _draw_distribution(
    rng: np.random.Generator,
    *,
    size: int,
    mean: float,
    std: float,
    distribution: str,
) -> np.ndarray:
    """Sample *size* draws from the configured distribution."""

    distribution = (distribution or "normal").lower()
    std = max(0.0, float(std))
    mean = float(mean)
    if std <= 0:
        return np.full(size, mean, dtype=float)
    if distribution == "triangular":
        spread = std * math.sqrt(6.0)
        samples = rng.triangular(mean - spread, mean, mean + spread, size)
    elif distribution == "uniform":
        spread = std * math.sqrt(3.0)
        samples = rng.uniform(mean - spread, mean + spread, size)
    else:
        samples = rng.normal(mean, std, size)
    return np.clip(samples, -0.5, 0.5)


@st.cache_data(show_spinner=False)
def run_monte_carlo(
    plan_data: Dict[str, object],
    capex_data: Dict[str, object],
    loans_data: Dict[str, object],
    tax_data: Dict[str, object],
    *,
    distributions: Dict[str, Dict[str, float]],
    metric_key: str,
    n_trials: int,
    seed: int,
) -> pd.DataFrame:
    if n_trials <= 0 or n_trials > 1000:
        raise ValueError("Monte Carlo trials must be between 1 and 1000.")

    plan_cfg = deserialize_plan_config(plan_data)
    capex = CapexPlan(**capex_data)
    loans = LoanSchedule(**loans_data)
    tax = TaxPolicy(**tax_data)

    rng = np.random.default_rng(seed)
    customers_cfg = distributions.get("customers", {})
    price_cfg = distributions.get("price", {})
    cost_cfg = distributions.get("cost", {})
    fixed_cfg = distributions.get("fixed", {})

    customers_draw = _draw_distribution(
        rng,
        size=n_trials,
        mean=customers_cfg.get("mean", 0.0),
        std=customers_cfg.get("std", 0.0),
        distribution=str(customers_cfg.get("distribution", "normal")),
    )
    price_draw = _draw_distribution(
        rng,
        size=n_trials,
        mean=price_cfg.get("mean", 0.0),
        std=price_cfg.get("std", 0.0),
        distribution=str(price_cfg.get("distribution", "normal")),
    )
    cost_draw = _draw_distribution(
        rng,
        size=n_trials,
        mean=cost_cfg.get("mean", 0.0),
        std=cost_cfg.get("std", 0.0),
        distribution=str(cost_cfg.get("distribution", "normal")),
    )
    fixed_draw = _draw_distribution(
        rng,
        size=n_trials,
        mean=fixed_cfg.get("mean", 0.0),
        std=fixed_cfg.get("std", 0.0),
        distribution=str(fixed_cfg.get("distribution", "normal")),
    )

    records: List[Dict[str, float]] = []
    for idx in range(n_trials):
        result = evaluate_scenario(
            plan_cfg,
            capex=capex,
            loans=loans,
            tax=tax,
            customers_change=Decimal(str(customers_draw[idx])),
            price_change=Decimal(str(price_draw[idx])),
            cost_change=Decimal(str(cost_draw[idx])),
            fixed_change=Decimal(str(fixed_draw[idx])),
        )
        records.append(
            {
                "Trial": idx + 1,
                "客数": float(customers_draw[idx] * 100.0),
                "客単価": float(price_draw[idx] * 100.0),
                "原価率": float(cost_draw[idx] * 100.0),
                "固定費": float(fixed_draw[idx] * 100.0),
                "売上高": float(result["sales"]),
                "粗利": float(result["gross"]),
                "EBIT": float(result["ebit"]),
                "FCF": float(result["fcf"]),
                "DSCR": float(result["dscr"]) if not Decimal(result["dscr"]).is_nan() else float("nan"),
                "Metric": float(_metric_value(result, metric_key)),
            }
        )
    return pd.DataFrame(records)


settings_state: Dict[str, object] = st.session_state.get("finance_settings", {})
unit = str(settings_state.get("unit", "百万円"))
fte = Decimal(str(settings_state.get("fte", 20)))

bundle, has_custom_inputs = load_finance_bundle()
if not has_custom_inputs:
    st.info("入力データが未保存のため、既定値でシナリオを算出しています。")

plan_cfg = plan_from_models(
    bundle.sales,
    bundle.costs,
    bundle.capex,
    bundle.loans,
    bundle.tax,
    fte=fte,
    unit=unit,
)

st.title("シナリオ / 感度分析")

scenario_tab, sensitivity_tab = st.tabs(["シナリオ比較", "感度・リスク分析"])


with scenario_tab:
    st.subheader("リスク閾値とシナリオ管理")
    st.caption("VaR・DSCRの閾値を定めたうえで、業務シナリオをデータエディタから柔軟に定義できます。")

    thresholds_state = st.session_state.get("scenario_thresholds", {}).copy()
    var_limit_state = thresholds_state.get("var_limit")
    dscr_floor_state = thresholds_state.get("dscr_floor", 1.2)
    var_conf_state = thresholds_state.get("var_confidence", 0.95)

    risk_cols = st.columns([1.6, 1.2, 1.2])
    var_enabled = risk_cols[0].checkbox(
        "VaR閾値を有効にする",
        value=var_limit_state is not None,
        help="フリーキャッシュフローが下回ると警告する最小許容値を設定します。",
        key="scenario_var_enabled",
    )
    var_limit_input = risk_cols[0].number_input(
        f"最小許容FCF ({unit})",
        value=float(var_limit_state or 0.0),
        step=0.5,
        format="%.1f",
        disabled=not var_enabled,
        help="マイナス値を指定すると許容損失額を表します。",
    )
    dscr_floor_input = risk_cols[1].number_input(
        "DSCR下限",
        min_value=0.0,
        max_value=5.0,
        value=float(dscr_floor_state or 1.2),
        step=0.1,
        format="%.2f",
        help="債務償還比率がこの値を下回ると警告します。",
    )
    var_conf_input = risk_cols[2].slider(
        "VaR信頼水準",
        min_value=0.80,
        max_value=0.99,
        value=float(var_conf_state or 0.95),
        step=0.01,
        help="モンテカルロ分析で損失額を評価する信頼水準です。",
    )

    st.session_state["scenario_thresholds"] = {
        "var_limit": float(var_limit_input) if var_enabled else None,
        "dscr_floor": float(dscr_floor_input) if dscr_floor_input > 0 else None,
        "var_confidence": float(var_conf_input),
    }

    scenario_df_state = st.session_state.get("scenario_df")
    if isinstance(scenario_df_state, pd.DataFrame):
        scenario_df = _sanitize_scenario_df(scenario_df_state)
    else:
        scenario_df = _sanitize_scenario_df(None)
    if not isinstance(scenario_df_state, pd.DataFrame) or not scenario_df_state.equals(scenario_df):
        st.session_state["scenario_df"] = scenario_df

    st.markdown("### シナリオ定義")
    st.caption("プリセットや独自メモを活用しながら、ベース・ベスト・ワースト以外のシナリオも自由に設計できます。")

    preset_col, add_col = st.columns([3, 1])
    preset_choice = preset_col.selectbox(
        "プリセットから追加",
        options=list(SCENARIO_PRESETS.keys()),
        format_func=lambda key: SCENARIO_PRESETS[key]["name"],
        key="scenario_preset_selector",
    )
    if add_col.button("プリセット追加", use_container_width=True):
        scenario_df = _append_preset_scenario(scenario_df, preset_choice)
        st.session_state["scenario_df"] = scenario_df

    edited_df = st.data_editor(
        scenario_df,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        column_config={
            "key": st.column_config.TextColumn("ID", disabled=True, width="small", help="内部識別子"),
            "name": st.column_config.TextColumn("シナリオ名", required=True),
            "customers_pct": st.column_config.NumberColumn("客数 (％)", min_value=-50.0, max_value=50.0, format="%.1f", step=1.0),
            "price_pct": st.column_config.NumberColumn("単価 (％)", min_value=-50.0, max_value=50.0, format="%.1f", step=1.0),
            "cost_pct": st.column_config.NumberColumn("原価率 (％)", min_value=-50.0, max_value=50.0, format="%.1f", step=1.0),
            "fixed_pct": st.column_config.NumberColumn("固定費 (％)", min_value=-50.0, max_value=50.0, format="%.1f", step=1.0),
            "notes": st.column_config.TextColumn("メモ", width="large"),
        },
    )

    sanitized_editor_df = _sanitize_scenario_df(edited_df if isinstance(edited_df, pd.DataFrame) else None)
    if not sanitized_editor_df.equals(scenario_df):
        scenario_df = sanitized_editor_df
        st.session_state["scenario_df"] = scenario_df

    thresholds = st.session_state["scenario_thresholds"]
    var_limit_threshold = thresholds.get("var_limit")
    dscr_floor_threshold = thresholds.get("dscr_floor")

    scenario_records = scenario_df.to_dict("records")
    scenario_results: Dict[str, Dict[str, Decimal]] = {}
    for record in scenario_records:
        scenario_results[record["key"]] = evaluate_scenario(
            plan_cfg,
            capex=bundle.capex,
            loans=bundle.loans,
            tax=bundle.tax,
            customers_change=_fraction(record.get("customers_pct", 0.0)),
            price_change=_fraction(record.get("price_pct", 0.0)),
            cost_change=_fraction(record.get("cost_pct", 0.0)),
            fixed_change=_fraction(record.get("fixed_pct", 0.0)),
        )

    display_rows: List[Dict[str, str]] = []
    chart_rows: List[Dict[str, float]] = []
    flagged_labels: List[str] = []
    for record in scenario_records:
        label = record.get("name", "Scenario")
        result = scenario_results.get(record["key"], {})
        risk_label = _scenario_risk_flags(
            result,
            var_limit=var_limit_threshold,
            dscr_floor=dscr_floor_threshold,
        )
        if risk_label != "—":
            flagged_labels.append(label)
        display_rows.append(
            {
                "シナリオ": label,
                "客数": _scenario_percent_label(float(record.get("customers_pct", 0.0))),
                "単価": _scenario_percent_label(float(record.get("price_pct", 0.0))),
                "原価率": _scenario_percent_label(float(record.get("cost_pct", 0.0))),
                "固定費": _scenario_percent_label(float(record.get("fixed_pct", 0.0))),
                "売上高": format_amount_with_unit(result.get("sales", Decimal("0")), unit),
                "粗利": format_amount_with_unit(result.get("gross", Decimal("0")), unit),
                "EBIT": format_amount_with_unit(result.get("ebit", Decimal("0")), unit),
                "FCF": format_amount_with_unit(result.get("fcf", Decimal("0")), unit),
                "DSCR": _format_multiple(result.get("dscr", Decimal("NaN"))),
                "リスク": risk_label,
                "メモ": record.get("notes", ""),
            }
        )
        chart_rows.append(
            {
                "シナリオ": label,
                "売上高": float(result.get("sales", Decimal("0"))),
                "粗利": float(result.get("gross", Decimal("0"))),
                "EBIT": float(result.get("ebit", Decimal("0"))),
                "FCF": float(result.get("fcf", Decimal("0"))),
                "DSCR": float(result.get("dscr", Decimal("0")))
                if not Decimal(result.get("dscr", Decimal("NaN"))).is_nan()
                else float("nan"),
            }
        )

    result_table = pd.DataFrame(display_rows)
    st.dataframe(
        result_table,
        hide_index=True,
        **use_container_width_kwargs(st.dataframe),
    )
    if flagged_labels:
        st.warning("リスク閾値を下回るシナリオ: " + ", ".join(flagged_labels))

    if chart_rows:
        chart_source = pd.melt(
            pd.DataFrame(chart_rows),
            id_vars="シナリオ",
            value_vars=["売上高", "粗利", "EBIT", "FCF"],
            var_name="指標",
            value_name="金額",
        )
        chart = (
            alt.Chart(chart_source)
            .mark_bar()
            .encode(
                x=alt.X("シナリオ:N", sort=None),
                y=alt.Y("金額:Q", axis=alt.Axis(format="~s")),
                color="シナリオ:N",
                column="指標:N",
            )
            .properties(height=260)
        )
        st.altair_chart(chart, use_container_width=True)


with sensitivity_tab:
    st.subheader("主要ドライバーのトルネード図")
    st.caption("客数・単価・原価率の上下変動がKPIへ与える影響を可視化します。")

    tornado_metric = st.selectbox("分析対象の指標", list(METRIC_LABELS.keys()), format_func=lambda x: METRIC_LABELS[x], key="tornado_metric")
    col_a, col_b, col_c, col_d = st.columns(4)
    customers_step = col_a.slider("客数変動幅 (±%)", min_value=1, max_value=30, value=10)
    price_step = col_b.slider("単価変動幅 (±%)", min_value=1, max_value=30, value=8)
    cost_step = col_c.slider("原価率変動幅 (±%)", min_value=1, max_value=30, value=6)
    fixed_step = col_d.slider("固定費変動幅 (±%)", min_value=1, max_value=30, value=5)

    base_result = evaluate_scenario(
        plan_cfg,
        capex=bundle.capex,
        loans=bundle.loans,
        tax=bundle.tax,
        customers_change=Decimal("0"),
        price_change=Decimal("0"),
        cost_change=Decimal("0"),
        fixed_change=Decimal("0"),
    )

    tornado_data: List[Dict[str, float]] = []
    driver_settings = {
        "customers": customers_step,
        "price": price_step,
        "cost": cost_step,
        "fixed": fixed_step,
    }
    for driver, magnitude in driver_settings.items():
        delta = _fraction(magnitude)
        high = evaluate_scenario(
            plan_cfg,
            capex=bundle.capex,
            loans=bundle.loans,
            tax=bundle.tax,
            customers_change=delta if driver == "customers" else Decimal("0"),
            price_change=delta if driver == "price" else Decimal("0"),
            cost_change=delta if driver == "cost" else Decimal("0"),
            fixed_change=delta if driver == "fixed" else Decimal("0"),
        )
        low = evaluate_scenario(
            plan_cfg,
            capex=bundle.capex,
            loans=bundle.loans,
            tax=bundle.tax,
            customers_change=-delta if driver == "customers" else Decimal("0"),
            price_change=-delta if driver == "price" else Decimal("0"),
            cost_change=-delta if driver == "cost" else Decimal("0"),
            fixed_change=-delta if driver == "fixed" else Decimal("0"),
        )
        base_value = _metric_value(base_result, tornado_metric)
        high_val = _metric_value(high, tornado_metric) - base_value
        low_val = _metric_value(low, tornado_metric) - base_value
        tornado_data.append(
            {
                "Driver": DRIVER_LABELS[driver],
                "Scenario": f"+{magnitude}%",
                "Impact": float(high_val),
            }
        )
        tornado_data.append(
            {
                "Driver": DRIVER_LABELS[driver],
                "Scenario": f"-{magnitude}%",
                "Impact": float(low_val),
            }
        )

    tornado_df = pd.DataFrame(tornado_data)
    tornado_df["abs"] = tornado_df["Impact"].abs()
    order = (
        tornado_df.groupby("Driver")["abs"].max().sort_values(ascending=False).index.tolist()
    )
    tornado_chart = (
        alt.Chart(tornado_df)
        .mark_bar()
        .encode(
            y=alt.Y("Driver:N", sort=order),
            x=alt.X("Impact:Q", axis=alt.Axis(format="~s")),
            color=alt.Color("Scenario:N", scale=alt.Scale(range=["#9BB1D4", "#F4A259"])),
            tooltip=["Driver", "Scenario", alt.Tooltip("Impact:Q", format="~s")],
        )
        .properties(height=260)
    )
    st.altair_chart(tornado_chart, use_container_width=True)

    st.markdown("---")
    st.subheader("単変量感度カーブ")

    driver_choice = st.selectbox("変動させるドライバー", list(DRIVER_LABELS.keys()), format_func=lambda x: DRIVER_LABELS[x])
    range_pct = st.slider("評価レンジ (±%)", min_value=5, max_value=50, value=20, step=5)
    steps = st.slider("分割数", min_value=5, max_value=21, value=11, step=2)

    span = np.linspace(-range_pct, range_pct, steps)
    sensitivity_rows: List[Dict[str, float]] = []
    for pct in span:
        change = _fraction(pct)
        result = evaluate_scenario(
            plan_cfg,
            capex=bundle.capex,
            loans=bundle.loans,
            tax=bundle.tax,
            customers_change=change if driver_choice == "customers" else Decimal("0"),
            price_change=change if driver_choice == "price" else Decimal("0"),
            cost_change=change if driver_choice == "cost" else Decimal("0"),
            fixed_change=change if driver_choice == "fixed" else Decimal("0"),
        )
        sensitivity_rows.append(
            {
                "変動率": float(pct),
                METRIC_LABELS[tornado_metric]: float(_metric_value(result, tornado_metric)),
            }
        )
    sensitivity_df = pd.DataFrame(sensitivity_rows)
    sensitivity_chart = (
        alt.Chart(sensitivity_df)
        .mark_line(point=True)
        .encode(
            x=alt.X("変動率:Q", title="変動率 (%)"),
            y=alt.Y(f"{METRIC_LABELS[tornado_metric]}:Q", axis=alt.Axis(format="~s")),
        )
        .properties(height=260)
    )
    st.altair_chart(sensitivity_chart, use_container_width=True)

    st.markdown("---")
    st.subheader("多変量感度分析")
    st.caption("最大5つのドライバーを同時に変化させ、指標の振れ幅を一覧できます。")

    multi_metric = st.selectbox(
        "評価指標",
        list(METRIC_LABELS.keys()),
        format_func=lambda key: METRIC_LABELS[key],
        index=list(METRIC_LABELS.keys()).index("fcf"),
        key="multi_metric",
    )
    default_multi = [key for key in ["customers", "price", "cost"] if key in DRIVER_LABELS]
    multi_drivers = st.multiselect(
        "同時に変動させるドライバー",
        list(DRIVER_LABELS.keys()),
        default=default_multi,
        max_selections=MAX_MULTI_DRIVERS,
        format_func=lambda key: DRIVER_LABELS[key],
        key="multi_drivers",
    )

    if len(multi_drivers) >= 2:
        range_cols = st.columns(len(multi_drivers))
        driver_ranges: Dict[str, int] = {}
        for idx, driver in enumerate(multi_drivers):
            driver_ranges[driver] = range_cols[idx].slider(
                f"{DRIVER_LABELS[driver]} 変動幅 (±%)",
                min_value=5,
                max_value=40,
                value=10,
                step=5,
                key=f"multi_range_{driver}",
            )

        base_metric_value = _metric_value(base_result, multi_metric)
        base_display = (
            _format_multiple(base_metric_value)
            if multi_metric == "dscr"
            else format_amount_with_unit(base_metric_value, unit)
        )
        st.caption(f"ベースライン値: {base_display}")

        combinations: List[Dict[str, object]] = []
        grids = [(-driver_ranges[d], 0, driver_ranges[d]) for d in multi_drivers]
        for deltas in itertools.product(*grids):
            change_map = dict(zip(multi_drivers, deltas))
            result = evaluate_scenario(
                plan_cfg,
                capex=bundle.capex,
                loans=bundle.loans,
                tax=bundle.tax,
                customers_change=_fraction(change_map.get("customers", 0.0)),
                price_change=_fraction(change_map.get("price", 0.0)),
                cost_change=_fraction(change_map.get("cost", 0.0)),
                fixed_change=_fraction(change_map.get("fixed", 0.0)),
            )
            metric_value = _metric_value(result, multi_metric)
            diff_value = metric_value - base_metric_value
            label_parts = [
                f"{DRIVER_LABELS[d]} {_scenario_percent_label(change_map[d])}"
                for d in multi_drivers
            ]
            label = " | ".join(label_parts)
            if multi_metric == "dscr":
                value_display = _format_multiple(metric_value)
                diff_display = f"{float(diff_value):+.2f}倍"
                axis_format = "0.00"
            else:
                value_display = format_amount_with_unit(metric_value, unit)
                diff_display = format_delta(diff_value, unit)
                axis_format = "~s"
            record: Dict[str, object] = {
                "ケース": label,
                "値": value_display,
                "差分": diff_display,
                "raw_value": float(metric_value),
                "raw_diff": float(diff_value),
            }
            for driver in multi_drivers:
                record[DRIVER_LABELS[driver]] = _scenario_percent_label(change_map[driver])
            record["axis_format"] = axis_format
            combinations.append(record)

        multi_df = pd.DataFrame(combinations)
        if not multi_df.empty:
            display_df = multi_df.drop(columns=["raw_value", "raw_diff", "axis_format"], errors="ignore")
            st.dataframe(
                display_df,
                hide_index=True,
                **use_container_width_kwargs(st.dataframe),
            )
            axis_format = multi_df["axis_format"].iloc[0] if "axis_format" in multi_df else "~s"
            sorted_cases = multi_df.sort_values("raw_value")
            order = sorted_cases["ケース"].tolist()
            multi_chart = (
                alt.Chart(sorted_cases)
                .mark_circle(size=80)
                .encode(
                    x=alt.X(
                        "raw_value:Q",
                        title=METRIC_LABELS[multi_metric],
                        axis=alt.Axis(format=axis_format),
                    ),
                    y=alt.Y("ケース:N", sort=order),
                    color=alt.Color(
                        "raw_diff:Q",
                        scale=alt.Scale(scheme="redblue", domainMid=0),
                        legend=alt.Legend(title="差分"),
                    ),
                    tooltip=[
                        "ケース",
                        alt.Tooltip("raw_value:Q", title=METRIC_LABELS[multi_metric], format=axis_format),
                        alt.Tooltip("raw_diff:Q", title="差分", format=axis_format),
                    ],
                )
                .properties(height=320)
            )
            st.altair_chart(multi_chart, use_container_width=True)
    else:
        st.info("2つ以上のドライバーを選択すると、多変量感度結果が表示されます。")

    st.markdown("---")
    st.subheader("二変量ヒートマップ")

    col_x, col_y = st.columns(2)
    var_x = col_x.selectbox(
        "横軸ドライバー",
        list(DRIVER_LABELS.keys()),
        format_func=lambda x: DRIVER_LABELS[x],
        key="heatmap_x",
    )
    available_y = [key for key in DRIVER_LABELS.keys() if key != var_x]
    var_y = col_y.selectbox(
        "縦軸ドライバー",
        available_y,
        format_func=lambda x: DRIVER_LABELS[x],
        key="heatmap_y",
    )
    heatmap_range = st.slider("ヒートマップ範囲 (±%)", min_value=5, max_value=50, value=15, step=5)
    grid_steps = st.slider("格子数", min_value=5, max_value=21, value=11, step=2)

    axis_values = np.linspace(-heatmap_range, heatmap_range, grid_steps)
    heatmap_rows: List[Dict[str, float]] = []
    for x_pct in axis_values:
        x_change = _fraction(x_pct)
        for y_pct in axis_values:
            y_change = _fraction(y_pct)
            result = evaluate_scenario(
                plan_cfg,
                capex=bundle.capex,
                loans=bundle.loans,
                tax=bundle.tax,
                customers_change=x_change if var_x == "customers" else (y_change if var_y == "customers" else Decimal("0")),
                price_change=x_change if var_x == "price" else (y_change if var_y == "price" else Decimal("0")),
                cost_change=x_change if var_x == "cost" else (y_change if var_y == "cost" else Decimal("0")),
                fixed_change=x_change if var_x == "fixed" else (y_change if var_y == "fixed" else Decimal("0")),
            )
            heatmap_rows.append(
                {
                    "横軸": float(x_pct),
                    "縦軸": float(y_pct),
                    "値": float(_metric_value(result, tornado_metric)),
                }
            )
    heatmap_df = pd.DataFrame(heatmap_rows)
    heatmap_chart = (
        alt.Chart(heatmap_df)
        .mark_rect()
        .encode(
            x=alt.X("横軸:Q", title=f"{DRIVER_LABELS[var_x]} 変動率 (%)"),
            y=alt.Y("縦軸:Q", title=f"{DRIVER_LABELS[var_y]} 変動率 (%)"),
            color=alt.Color("値:Q", scale=alt.Scale(scheme="blueorange"), title=METRIC_LABELS[tornado_metric]),
        )
        .properties(height=320)
    )
    st.altair_chart(heatmap_chart, use_container_width=True)

    st.markdown("---")
    st.subheader("モンテカルロ・シミュレーション")

    mc_config_state = st.session_state.setdefault(
        "scenario_mc_config",
        {key: value.copy() for key, value in DEFAULT_MC_CONFIG.items()},
    )

    with st.expander("試行設定", expanded=False):
        st.caption("乱数分布と平均・標準偏差（％）を設定できます。")
        config_updates: Dict[str, Dict[str, float | str]] = {}
        for driver_key, driver_label in DRIVER_LABELS.items():
            st.markdown(f"**{driver_label}**")
            cfg = mc_config_state.get(driver_key, DEFAULT_MC_CONFIG.get(driver_key, {})).copy()
            col_dist, col_mean, col_std = st.columns([1.2, 1, 1])
            dist_options = list(DISTRIBUTION_OPTIONS.keys())
            default_dist = str(cfg.get("distribution", "normal"))
            dist_index = dist_options.index(default_dist) if default_dist in dist_options else 0
            distribution = col_dist.selectbox(
                "分布",
                dist_options,
                index=dist_index,
                format_func=lambda key: DISTRIBUTION_OPTIONS[key],
                key=f"mc_dist_{driver_key}",
            )
            mean_pct = col_mean.number_input(
                "平均 (%)",
                value=float(cfg.get("mean_pct", 0.0)),
                step=0.5,
                format="%.2f",
                key=f"mc_mean_{driver_key}",
            )
            std_pct = col_std.number_input(
                "標準偏差 (%)",
                value=float(cfg.get("std_pct", 0.0)),
                min_value=0.0,
                max_value=50.0,
                step=0.5,
                format="%.2f",
                key=f"mc_std_{driver_key}",
            )
            config_updates[driver_key] = {
                "distribution": distribution,
                "mean_pct": mean_pct,
                "std_pct": std_pct,
            }
        st.session_state["scenario_mc_config"] = config_updates

        mc_trials = st.slider("試行回数", min_value=100, max_value=1000, value=400, step=50)
        if mc_trials > 700:
            st.warning("試行回数が多いため、再計算に時間がかかる可能性があります。")
        mc_seed = st.number_input("乱数シード", min_value=0, max_value=9999, value=42, step=1)
        metric_for_mc = st.selectbox(
            "注目指標",
            list(METRIC_LABELS.keys()),
            index=list(METRIC_LABELS.keys()).index("fcf"),
            format_func=lambda x: METRIC_LABELS[x],
            key="mc_metric",
        )
        run_button = st.button("モンテカルロを実行", key="mc_run_button")

    distribution_payload: Dict[str, Dict[str, float | str]] = {}
    current_mc_cfg = st.session_state.get("scenario_mc_config", {})
    for driver_key in DRIVER_LABELS.keys():
        cfg = current_mc_cfg.get(driver_key, DEFAULT_MC_CONFIG.get(driver_key, {}))
        distribution_payload[driver_key] = {
            "distribution": cfg.get("distribution", "normal"),
            "mean": float(cfg.get("mean_pct", 0.0)) / 100.0,
            "std": float(cfg.get("std_pct", 0.0)) / 100.0,
        }

    if run_button:
        plan_serialized = serialize_plan_config(plan_cfg)
        capex_dump = bundle.capex.model_dump(mode="json")
        loans_dump = bundle.loans.model_dump(mode="json")
        tax_dump = bundle.tax.model_dump(mode="json")
        try:
            mc_df = run_monte_carlo(
                plan_serialized,
                capex_dump,
                loans_dump,
                tax_dump,
                distributions=distribution_payload,
                metric_key=metric_for_mc,
                n_trials=int(mc_trials),
                seed=int(mc_seed),
            )
            st.session_state["scenario_mc_df"] = mc_df
        except ValueError as exc:
            st.error(str(exc))
            st.session_state.pop("scenario_mc_df", None)

    thresholds_risk = st.session_state.get("scenario_thresholds", {})
    var_confidence = float(thresholds_risk.get("var_confidence", 0.95))
    var_limit_threshold = thresholds_risk.get("var_limit")
    dscr_floor_threshold = thresholds_risk.get("dscr_floor")

    mc_df_session = st.session_state.get("scenario_mc_df")
    if isinstance(mc_df_session, pd.DataFrame) and not mc_df_session.empty:
        metric_label = METRIC_LABELS.get(metric_for_mc, "指標")
        st.markdown(f"**{metric_label} の試行結果**")
        summary = mc_df_session["Metric"].describe(percentiles=[0.05, 0.5, 0.95]).rename(
            index={"5%": "P5", "50%": "Median", "95%": "P95"}
        )
        st.table(summary.to_frame(name="値"))

        histogram = (
            alt.Chart(mc_df_session)
            .mark_area(opacity=0.6)
            .encode(
                x=alt.X("Metric:Q", title=metric_label, bin=alt.Bin(maxbins=40)),
                y=alt.Y("count():Q", title="頻度"),
            )
            .properties(height=260)
        )
        profit_curve = _profit_curve_frame(mc_df_session.get("Metric"))
        chart_cols = st.columns(2)
        chart_cols[0].altair_chart(histogram, use_container_width=True)
        if not profit_curve.empty:
            curve_chart = (
                alt.Chart(profit_curve)
                .mark_line()
                .encode(
                    x=alt.X("Metric:Q", title=metric_label),
                    y=alt.Y("累積確率:Q", scale=alt.Scale(domain=[0, 1])),
                )
                .properties(height=260)
            )
            chart_cols[1].altair_chart(curve_chart, use_container_width=True)
        else:
            chart_cols[1].info("十分なデータがないため、損益曲線を描画できません。")

        fcf_series = mc_df_session["FCF"].dropna()
        if not fcf_series.empty:
            quantile = max(0.0, min(1.0, 1.0 - var_confidence))
            var_value = float(fcf_series.quantile(quantile))
            failure_probability = float((fcf_series < 0).mean())
        else:
            var_value = float("nan")
            failure_probability = float("nan")

        if dscr_floor_threshold is not None:
            dscr_series = mc_df_session["DSCR"].dropna()
            dscr_shortfall = float((dscr_series < dscr_floor_threshold).mean()) if not dscr_series.empty else float("nan")
        else:
            dscr_shortfall = float("nan")

        metrics_cols = st.columns(3)
        if math.isnan(var_value):
            var_display = "—"
        else:
            var_display = format_amount_with_unit(Decimal(str(var_value)), unit)
        metrics_cols[0].metric(f"VaR ({var_confidence * 100:.0f}%信頼)", var_display)

        failure_display = f"{failure_probability * 100:.1f}%" if not math.isnan(failure_probability) else "—"
        metrics_cols[1].metric("資金ショート確率", failure_display)

        if dscr_floor_threshold is not None and not math.isnan(dscr_shortfall):
            dscr_display = f"{dscr_shortfall * 100:.1f}%"
        else:
            dscr_display = "—"
        metrics_cols[2].metric("DSCR下限割れ確率", dscr_display)

        if (
            var_limit_threshold is not None
            and not math.isnan(var_value)
            and var_value < float(var_limit_threshold)
        ):
            st.error(
                "VaRが設定した閾値を下回っています: "
                + format_amount_with_unit(Decimal(str(var_limit_threshold)), unit)
            )
        if dscr_floor_threshold is not None and not math.isnan(dscr_shortfall) and dscr_shortfall > 0:
            st.warning(
                f"DSCRが下限 {float(dscr_floor_threshold):.2f} を下回る確率: {dscr_shortfall * 100:.1f}%"
            )
    else:
        st.info("モンテカルロ試行を実行すると、結果がここに表示されます。")
