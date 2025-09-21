"""Scenario planning and sensitivity analysis dashboard."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from calc import compute, generate_cash_flow, plan_from_models, summarize_plan_metrics
from formatting import format_amount_with_unit
from models import CapexPlan, LoanSchedule, TaxPolicy
from state import ensure_session_defaults, load_finance_bundle
from theme import inject_theme

st.set_page_config(
    page_title="経営計画スタジオ｜Scenarios",
    page_icon="🧮",
    layout="wide",
)

inject_theme()
ensure_session_defaults()

DRIVER_LABELS: Dict[str, str] = {
    "customers": "客数",
    "price": "客単価",
    "cost": "原価率",
}

METRIC_LABELS: Dict[str, str] = {
    "sales": "売上高",
    "gross": "粗利",
    "ebit": "EBIT (営業利益)",
    "ord": "経常利益",
    "fcf": "FCF",
    "dscr": "DSCR",
}

DEFAULT_SCENARIOS: Dict[str, Dict[str, float]] = {
    "baseline": {"name": "Baseline", "customers_pct": 0.0, "price_pct": 0.0, "cost_pct": 0.0},
    "best": {"name": "Best", "customers_pct": 8.0, "price_pct": 5.0, "cost_pct": -4.0},
    "worst": {"name": "Worst", "customers_pct": -6.0, "price_pct": -3.0, "cost_pct": 4.0},
}

COGS_CODES = ["COGS_MAT", "COGS_LBR", "COGS_OUT_SRC", "COGS_OUT_CON", "COGS_OTH"]


def _decimal(value: float | Decimal) -> Decimal:
    """Return *value* as :class:`~decimal.Decimal`."""

    return Decimal(str(value))


def _fraction(value_pct: float | Decimal) -> Decimal:
    """Convert a percentage value into a decimal fraction."""

    return _decimal(value_pct) / Decimal("100")


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
) -> Dict[str, Decimal]:
    plan = plan_cfg if cost_change == Decimal("0") else plan_cfg.clone()
    if cost_change != 0:
        factor = Decimal("1") + cost_change
        for code in COGS_CODES:
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
) -> Dict[str, Decimal]:
    """Evaluate a scenario and return core metrics."""

    amounts = _scenario_amounts(
        plan_cfg,
        customers_change=customers_change,
        price_change=price_change,
        cost_change=cost_change,
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


@st.cache_data(show_spinner=False)
def run_monte_carlo(
    plan_data: Dict[str, object],
    capex_data: Dict[str, object],
    loans_data: Dict[str, object],
    tax_data: Dict[str, object],
    *,
    customers_std: float,
    price_std: float,
    cost_std: float,
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
    customers_draw = rng.normal(loc=0.0, scale=customers_std, size=n_trials)
    price_draw = rng.normal(loc=0.0, scale=price_std, size=n_trials)
    cost_draw = rng.normal(loc=0.0, scale=cost_std, size=n_trials)

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
        )
        records.append(
            {
                "Trial": idx + 1,
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

st.title("🧮 シナリオ / 感度分析")

scenario_tab, sensitivity_tab = st.tabs(["シナリオ比較", "感度・リスク分析"])


with scenario_tab:
    st.subheader("ベース / ベスト / ワースト シナリオ")
    st.caption("客数・単価・原価率の変動を設定し、主要指標を比較します。")

    stored_configs = st.session_state.setdefault(
        "scenario_configs",
        {key: value.copy() for key, value in DEFAULT_SCENARIOS.items()},
    )
    with st.form("scenario_form"):
        st.write("シナリオ別の変動率(%)を入力し、下のボタンで更新します。")
        new_configs: Dict[str, Dict[str, float]] = {}
        cols = st.columns(3)
        keys = ["baseline", "best", "worst"]
        for idx, key in enumerate(keys):
            cfg = stored_configs.get(key, DEFAULT_SCENARIOS[key]).copy()
            with cols[idx]:
                st.markdown(f"#### {cfg.get('name', DEFAULT_SCENARIOS[key]['name'])}")
                name = st.text_input("ラベル", value=cfg.get("name", DEFAULT_SCENARIOS[key]["name"]), key=f"name_{key}")
                customers = st.number_input(
                    "客数", value=float(cfg.get("customers_pct", 0.0)), format="%.1f",
                    min_value=-50.0, max_value=50.0, step=1.0, key=f"cust_{key}"
                )
                price = st.number_input(
                    "客単価", value=float(cfg.get("price_pct", 0.0)), format="%.1f",
                    min_value=-50.0, max_value=50.0, step=1.0, key=f"price_{key}"
                )
                cost = st.number_input(
                    "原価率", value=float(cfg.get("cost_pct", 0.0)), format="%.1f",
                    min_value=-50.0, max_value=50.0, step=1.0, key=f"cost_{key}"
                )
                new_configs[key] = {
                    "name": name.strip() or DEFAULT_SCENARIOS[key]["name"],
                    "customers_pct": float(customers),
                    "price_pct": float(price),
                    "cost_pct": float(cost),
                }
        submitted = st.form_submit_button("📊 シナリオを再計算")

    if submitted:
        st.session_state["scenario_configs"] = new_configs
        stored_configs = new_configs

    results: Dict[str, Dict[str, Decimal]] = {}
    for key, cfg in stored_configs.items():
        results[key] = evaluate_scenario(
            plan_cfg,
            capex=bundle.capex,
            loans=bundle.loans,
            tax=bundle.tax,
            customers_change=_fraction(cfg.get("customers_pct", 0.0)),
            price_change=_fraction(cfg.get("price_pct", 0.0)),
            cost_change=_fraction(cfg.get("cost_pct", 0.0)),
        )

    display_rows: List[Dict[str, str]] = []
    chart_rows: List[Dict[str, float]] = []
    for key in keys:
        cfg = stored_configs[key]
        result = results.get(key, {})
        label = cfg.get("name", DEFAULT_SCENARIOS[key]["name"])
        display_rows.append(
            {
                "シナリオ": label,
                "売上高": format_amount_with_unit(result.get("sales", Decimal("0")), unit),
                "粗利": format_amount_with_unit(result.get("gross", Decimal("0")), unit),
                "EBIT": format_amount_with_unit(result.get("ebit", Decimal("0")), unit),
                "FCF": format_amount_with_unit(result.get("fcf", Decimal("0")), unit),
                "DSCR": _format_multiple(result.get("dscr", Decimal("NaN"))),
            }
        )
        chart_rows.append(
            {
                "シナリオ": label,
                "売上高": float(result.get("sales", Decimal("0"))),
                "粗利": float(result.get("gross", Decimal("0"))),
                "EBIT": float(result.get("ebit", Decimal("0"))),
                "FCF": float(result.get("fcf", Decimal("0"))),
                "DSCR": float(result.get("dscr", Decimal("0"))) if not Decimal(result.get("dscr", Decimal("NaN"))).is_nan() else float("nan"),
            }
        )

    table_df = pd.DataFrame(display_rows)
    st.dataframe(table_df, hide_index=True, use_container_width=True)

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
    col_a, col_b, col_c = st.columns(3)
    customers_step = col_a.slider("客数変動幅 (±%)", min_value=1, max_value=30, value=10)
    price_step = col_b.slider("単価変動幅 (±%)", min_value=1, max_value=30, value=8)
    cost_step = col_c.slider("原価率変動幅 (±%)", min_value=1, max_value=30, value=6)

    base_result = evaluate_scenario(
        plan_cfg,
        capex=bundle.capex,
        loans=bundle.loans,
        tax=bundle.tax,
        customers_change=Decimal("0"),
        price_change=Decimal("0"),
        cost_change=Decimal("0"),
    )

    tornado_data: List[Dict[str, float]] = []
    driver_settings = {
        "customers": customers_step,
        "price": price_step,
        "cost": cost_step,
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
        )
        low = evaluate_scenario(
            plan_cfg,
            capex=bundle.capex,
            loans=bundle.loans,
            tax=bundle.tax,
            customers_change=-delta if driver == "customers" else Decimal("0"),
            price_change=-delta if driver == "price" else Decimal("0"),
            cost_change=-delta if driver == "cost" else Decimal("0"),
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

    with st.expander("🎲 ランダム試行設定", expanded=False):
        st.caption("乱数試行は最大1,000回までです。標準偏差は割合で指定します。")
        mc_col1, mc_col2, mc_col3 = st.columns(3)
        customers_std = mc_col1.number_input("客数標準偏差 (%)", min_value=0.0, max_value=30.0, value=3.0, step=0.5)
        price_std = mc_col2.number_input("単価標準偏差 (%)", min_value=0.0, max_value=30.0, value=2.0, step=0.5)
        cost_std = mc_col3.number_input("原価率標準偏差 (%)", min_value=0.0, max_value=30.0, value=1.5, step=0.5)
        mc_trials = st.slider("試行回数", min_value=100, max_value=1000, value=400, step=50)
        mc_seed = st.number_input("乱数シード", min_value=0, max_value=9999, value=42, step=1)
        metric_for_mc = st.selectbox(
            "注目指標",
            list(METRIC_LABELS.keys()),
            index=list(METRIC_LABELS.keys()).index("fcf"),
            format_func=lambda x: METRIC_LABELS[x],
            key="mc_metric",
        )
        run_button = st.button("🎯 モンテカルロを実行")

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
                customers_std=customers_std / 100.0,
                price_std=price_std / 100.0,
                cost_std=cost_std / 100.0,
                metric_key=metric_for_mc,
                n_trials=mc_trials,
                seed=int(mc_seed),
            )
            st.session_state["scenario_mc_df"] = mc_df
        except ValueError as exc:
            st.error(str(exc))
            st.session_state.pop("scenario_mc_df", None)

    mc_df_session = st.session_state.get("scenario_mc_df")
    if isinstance(mc_df_session, pd.DataFrame) and not mc_df_session.empty:
        metric_label = METRIC_LABELS.get(metric_for_mc, "指標")
        st.markdown(f"**{metric_label} の試行結果**")
        summary = mc_df_session["Metric"].describe(percentiles=[0.05, 0.5, 0.95]).rename(index={"5%": "P5", "50%": "Median", "95%": "P95"})
        summary_df = summary.to_frame(name="値")
        st.table(summary_df)
        chart = (
            alt.Chart(mc_df_session)
            .mark_area(opacity=0.6)
            .encode(
                x=alt.X("Metric:Q", title=metric_label, bin=alt.Bin(maxbins=40)),
                y=alt.Y("count():Q", title="頻度"),
            )
            .properties(height=260)
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("モンテカルロ試行を実行すると、結果がここに表示されます。")
