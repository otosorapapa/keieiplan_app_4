"""Utilities for managing Streamlit session state defaults and resets."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping, Tuple

import pandas as pd
import streamlit as st

from models import (
    DEFAULT_CAPEX_PLAN,
    DEFAULT_COST_PLAN,
    DEFAULT_LOAN_SCHEDULE,
    DEFAULT_SALES_PLAN,
    DEFAULT_TAX_POLICY,
    FinanceBundle,
)

StateFactory = Callable[[], Any]
TypeHint = type | tuple[type, ...] | None


@dataclass(frozen=True)
class StateSpec:
    """Definition of a session state entry."""

    default_factory: StateFactory
    type_hint: TypeHint
    description: str

    def create_default(self) -> Any:
        """Return a new default value for the state entry."""
        return self.default_factory()

    def is_valid(self, value: Any) -> bool:
        """Check whether *value* matches the declared type hint."""
        if self.type_hint is None:
            return True
        hints = self.type_hint if isinstance(self.type_hint, tuple) else (self.type_hint,)
        return isinstance(value, hints)


STATE_SPECS: Dict[str, StateSpec] = {
    "show_usage_guide": StateSpec(lambda: False, bool, "ヘルプ表示トグル"),
    "sensitivity_zoom_mode": StateSpec(lambda: False, bool, "感応度グラフ拡大モード"),
    "sensitivity_current": StateSpec(dict, dict, "感応度ビュー設定"),
    "kpi_history": StateSpec(dict, dict, "KPIメトリック履歴"),
    "metrics_timeline": StateSpec(list, list, "KPI推移の履歴"),
    "scenario_df": StateSpec(lambda: None, (pd.DataFrame, type(None)), "シナリオ設定データフレーム"),
    "scenario_editor": StateSpec(dict, dict, "シナリオエディタ状態"),
    "scenarios": StateSpec(list, (list, tuple, dict), "シナリオ保存データ"),
    "overrides": StateSpec(dict, dict, "金額上書き値"),
    "sidebar_step": StateSpec(lambda: "①データ入力", str, "サイドバーナビの選択ステップ"),
    "last_updated_ts": StateSpec(lambda: "", str, "最終更新タイムスタンプ"),
    "validation_status": StateSpec(lambda: "—", str, "検証ステータス表示"),
    "what_if_presets": StateSpec(dict, dict, "What-ifプリセット"),
    "what_if_scenarios": StateSpec(dict, dict, "What-ifシナリオ集合"),
    "what_if_default_quantity": StateSpec(lambda: None, (float, int, type(None)), "数量の既定値"),
    "what_if_default_customers": StateSpec(lambda: None, (float, int, type(None)), "顧客数の既定値"),
    "what_if_product_share": StateSpec(lambda: 0.6, (float, int), "製品売上比率の初期値"),
    "what_if_active": StateSpec(lambda: "A", str, "現在アクティブなWhat-ifシナリオ"),
    "finance_raw": StateSpec(dict, dict, "財務入力フォームの生データ"),
    "finance_models": StateSpec(dict, dict, "検証済みの財務モデル"),
    "finance_settings": StateSpec(
        lambda: {"unit": "百万円", "language": "ja", "fte": 20.0, "fiscal_year": 2025},
        dict,
        "共通設定（単位・言語・FTEなど）",
    ),
    "selected_industry_template": StateSpec(lambda: "", str, "選択された業種テンプレートキー"),
    "working_capital_profile": StateSpec(
        lambda: {"receivable_days": 45.0, "inventory_days": 30.0, "payable_days": 25.0},
        dict,
        "運転資本の想定（売掛・棚卸・買掛の回転日数）",
    ),
    "custom_kpi_selection": StateSpec(list, list, "ユーザーが選択したKPIカード"),
    "industry_custom_metrics": StateSpec(dict, dict, "業種別KPI計算設定"),
    "external_actuals": StateSpec(dict, dict, "外部データから取り込んだ実績値"),
    "scenario_thresholds": StateSpec(
        lambda: {"var_limit": None, "dscr_floor": 1.2, "var_confidence": 0.95},
        dict,
        "リスク管理用のVaR・DSCR閾値設定",
    ),
}


def ensure_session_defaults(overrides: Mapping[str, Any] | None = None) -> None:
    """Populate :mod:`st.session_state` with defaults and type-validate entries."""

    overrides = overrides or {}
    for key, spec in STATE_SPECS.items():
        if key in overrides:
            st.session_state[key] = overrides[key]
            continue
        if key not in st.session_state or not spec.is_valid(st.session_state[key]):
            st.session_state[key] = spec.create_default()


def reset_session_keys(keys: Iterable[str] | None = None) -> None:
    """Reset selected state keys to their default values."""

    target_keys = list(keys) if keys is not None else list(STATE_SPECS.keys())
    for key in target_keys:
        if key in STATE_SPECS:
            st.session_state[key] = STATE_SPECS[key].create_default()
        elif key in st.session_state:
            del st.session_state[key]


def reset_app_state(preserve: Iterable[str] | None = None) -> None:
    """Clear the current session state and re-apply defaults."""

    preserved = set(preserve or [])
    for key in list(st.session_state.keys()):
        if key not in preserved:
            del st.session_state[key]
    ensure_session_defaults()


def load_finance_bundle() -> Tuple[FinanceBundle, bool]:
    """Return the validated finance bundle from session or defaults.

    Returns a tuple of ``(bundle, is_custom)`` where *is_custom* indicates
    whether the bundle originates from user-supplied inputs (``True``) or if
    the defaults had to be used (``False``).
    """

    models_state: Dict[str, object] = st.session_state.get("finance_models", {})
    required_keys = {"sales", "costs", "capex", "loans", "tax"}
    if required_keys.issubset(models_state.keys()):
        try:
            bundle = FinanceBundle(
                sales=models_state["sales"],
                costs=models_state["costs"],
                capex=models_state["capex"],
                loans=models_state["loans"],
                tax=models_state["tax"],
            )
            return bundle, True
        except Exception:  # pragma: no cover - defensive guard
            pass

    default_bundle = FinanceBundle(
        sales=DEFAULT_SALES_PLAN.model_copy(deep=True),
        costs=DEFAULT_COST_PLAN.model_copy(deep=True),
        capex=DEFAULT_CAPEX_PLAN.model_copy(deep=True),
        loans=DEFAULT_LOAN_SCHEDULE.model_copy(deep=True),
        tax=DEFAULT_TAX_POLICY.model_copy(deep=True),
    )
    return default_bundle, False


__all__ = [
    "StateSpec",
    "STATE_SPECS",
    "ensure_session_defaults",
    "reset_session_keys",
    "reset_app_state",
    "load_finance_bundle",
]
