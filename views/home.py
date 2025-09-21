"""Render logic for the overview / tutorial home page."""
from __future__ import annotations

from decimal import Decimal
from typing import Dict

import streamlit as st

from calc import compute, plan_from_models, summarize_plan_metrics
from formatting import format_amount_with_unit, format_ratio
from state import ensure_session_defaults, load_finance_bundle, reset_app_state
from theme import inject_theme
from ui.chrome import HeaderActions, render_app_footer, render_app_header, render_usage_guide_panel


def render_home_page() -> None:
    """Render the home/overview page that appears in both root and pages menu."""

    inject_theme()
    ensure_session_defaults()

    header_actions: HeaderActions = render_app_header(
        title="経営計画スタジオ",
        subtitle="入力→分析→シナリオ→レポートをワンストップで。型安全な計算ロジックで意思決定をサポートします。",
    )

    if header_actions.reset_requested:
        reset_app_state()
        st.experimental_rerun()

    if header_actions.toggled_help:
        st.session_state["show_usage_guide"] = not st.session_state.get("show_usage_guide", False)

    render_usage_guide_panel()

    with st.container():
        st.markdown(
            """
            <div class="hero-card">
                <h1>McKinsey Inspired 経営計画ダッシュボード</h1>
                <p>チャネル×商品×月次の売上設計からKPI分析、シナリオ比較、ドキュメント出力までを一気通貫で支援します。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    settings_state: Dict[str, object] = st.session_state.get("finance_settings", {})
    unit = str(settings_state.get("unit", "百万円"))
    fte = Decimal(str(settings_state.get("fte", 20)))
    fiscal_year = int(settings_state.get("fiscal_year", 2025))

    bundle, has_custom_inputs = load_finance_bundle()

    summary_tab, tutorial_tab = st.tabs(["概要", "チュートリアル"])

    with summary_tab:
        st.subheader("📌 現状サマリー")

        if not has_custom_inputs:
            st.info("入力ページでデータを保存すると、ここに最新のKPIが表示されます。")

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

        metric_cols = st.columns(4)
        metric_cols[0].metric("売上高", format_amount_with_unit(amounts.get("REV", Decimal("0")), unit))
        metric_cols[1].metric("粗利率", format_ratio(metrics.get("gross_margin")))
        metric_cols[2].metric("経常利益", format_amount_with_unit(amounts.get("ORD", Decimal("0")), unit))
        metric_cols[3].metric("損益分岐点売上高", format_amount_with_unit(metrics.get("breakeven"), unit))

        st.caption(f"FY{fiscal_year} 計画 ｜ 表示単位: {unit} ｜ FTE: {fte}")

        st.markdown("### 次のステップ")
        st.markdown(
            """
            1. **Inputs** ページで売上・原価・費用・投資・借入・税制を登録する
            2. **Analysis** ページでPL/BS/CFとKPIを確認し、損益分岐点や資金繰りをチェック
            3. **Scenarios** ページで感度分析やシナリオ比較を行い、意思決定を支援
            4. **Report** ページでPDF / Excel / Word を生成し、ステークホルダーと共有
            5. **Settings** ページで単位や言語、既定値をカスタマイズ
            """
        )

    with tutorial_tab:
        st.subheader("🧭 チュートリアル")
        st.markdown(
            """
            - **セッションの保持**: サイドバーのページ遷移でも入力値はセッションステートに保存されます。
            - **URLダイレクトアクセス**: 各ページは初期化時に既定値をロードし、入力が無くても破綻しないようにガードしています。
            - **型安全な計算**: すべての計算は Pydantic モデルを通じて検証され、通貨は Decimal 基本で処理されます。
            - **エラーハンドリング**: 入力チェックに失敗すると、赤いトーストとフィールド強調で異常値を通知します。
            """
        )

    render_app_footer(
        caption="© 経営計画スタジオ | 情報設計の最適化と精緻な財務モデリングを提供します。",
    )
