"""Application settings for unit, language and default data."""
from __future__ import annotations

import json
from typing import Dict

import streamlit as st

from models import (
    DEFAULT_CAPEX_PLAN,
    DEFAULT_COST_PLAN,
    DEFAULT_LOAN_SCHEDULE,
    DEFAULT_SALES_PLAN,
    DEFAULT_TAX_POLICY,
)
from state import ensure_session_defaults
from theme import inject_theme
from services import auth
from ui.streamlit_compat import use_container_width_kwargs

st.set_page_config(
    page_title="経営計画スタジオ｜Settings",
    page_icon="⚙️",
    layout="wide",
)

inject_theme()
ensure_session_defaults()

settings_state: Dict[str, object] = st.session_state.get("finance_settings", {})
unit = str(settings_state.get("unit", "百万円"))
fte = float(settings_state.get("fte", 20.0))
fiscal_year = int(settings_state.get("fiscal_year", 2025))
language = str(settings_state.get("language", "ja"))

st.title("⚙️ アプリ設定")
st.caption("表示単位や言語、既定値、データバックアップを管理できます。")

unit_tab, language_tab, defaults_tab, backup_tab = st.tabs([
    "単位・期間",
    "言語",
    "既定値リセット",
    "バックアップ・セキュリティ",
])

with unit_tab:
    st.subheader("単位と会計期間")
    unit = st.selectbox("表示単位", ["百万円", "千円", "円"], index=["百万円", "千円", "円"].index(unit))
    fiscal_year = st.number_input("会計年度", min_value=2000, max_value=2100, step=1, value=fiscal_year)
    fte = st.number_input("FTE (人)", min_value=0.0, step=0.5, value=fte)

with language_tab:
    st.subheader("言語設定")
    language = st.selectbox("UI言語", ["ja", "en"], index=["ja", "en"].index(language) if language in {"ja", "en"} else 0)
    if language == "ja":
        st.caption("日本語UIを使用中です。英語UIは現在ベータ版です。")
    else:
        st.caption("English UI is experimental. Some strings may remain in Japanese.")

with defaults_tab:
    st.subheader("既定値のリセット")
    st.caption("入力データを初期値に戻す場合は以下のボタンを使用してください。")
    if st.button("既定値で再初期化", type="secondary"):
        st.session_state["finance_raw"] = {
            "sales": DEFAULT_SALES_PLAN.model_dump(),
            "costs": DEFAULT_COST_PLAN.model_dump(),
            "capex": DEFAULT_CAPEX_PLAN.model_dump(),
            "loans": DEFAULT_LOAN_SCHEDULE.model_dump(),
            "tax": DEFAULT_TAX_POLICY.model_dump(),
        }
        st.session_state.pop("finance_models", None)
        st.toast("既定値にリセットしました。", icon="✅")

if st.button("設定を保存", type="primary"):
        st.session_state["finance_settings"] = {
            "unit": unit,
            "language": language,
            "fte": float(fte),
            "fiscal_year": int(fiscal_year),
        }
        st.toast("設定を保存しました。", icon="✅")

with backup_tab:
    st.subheader("バックアップとセキュリティ")
    if not auth.is_authenticated():
        st.info("ログインすると保存データのバックアップをダウンロードできます。")
    else:
        current_user = auth.get_current_user()
        if current_user:
            st.caption(f"ログイン中: {current_user.email}")
        backup_payload = auth.export_backup() or {}
        backup_bytes = json.dumps(backup_payload, ensure_ascii=False, indent=2).encode("utf-8")
        st.download_button(
            "📥 JSONバックアップをダウンロード",
            data=backup_bytes,
            file_name="keieiplan_backup.json",
            mime="application/json",
            **use_container_width_kwargs(st.download_button),
        )
        st.caption("バックアップにはクラウドに保存した全ての計画とバージョン履歴が含まれます。")
        st.markdown(
            "- 通信は自動的にHTTPSへリダイレクトされます。\n"
            "- パスワードはbcryptでハッシュ化され、平文では保存されません。\n"
            "- 不要になったデータは [Inputs] ページでバージョン削除予定です。"
        )
