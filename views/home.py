"""Render logic for the overview / tutorial home page."""
from __future__ import annotations

from decimal import Decimal
from typing import Dict

import streamlit as st

from calc import compute, plan_from_models, summarize_plan_metrics
from formatting import format_amount_with_unit, format_ratio
from state import ensure_session_defaults, load_finance_bundle, reset_app_state
from theme import inject_theme
from services import auth
from ui.chrome import HeaderActions, render_app_footer, render_app_header, render_usage_guide_panel
from ui.components import MetricCard, render_callout, render_metric_cards


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

    if header_actions.logout_requested:
        st.experimental_rerun()

    if header_actions.toggled_help:
        st.session_state["show_usage_guide"] = not st.session_state.get("show_usage_guide", False)

    render_usage_guide_panel()

    with st.container():
        st.markdown(
            """
            <div class="hero-card">
                <h1>McKinsey Inspired 経営計画ダッシュボード</h1>
                <p>小規模事業者のためのAI駆動型経営計画スタジオ。財務モデリングから戦略立案、レポート化までを1つのワークスペースで完結させ、投資家や金融機関への説明資料をプロフェッショナル品質で仕上げます。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
        <div class="trust-badges" role="list" aria-label="信頼性に関するバッジ">
            <div class="trust-badge" role="listitem">
                <span class="trust-badge__icon" aria-hidden="true">🛡️</span>
                <span class="trust-badge__text">データは暗号化され、ISO/IEC 27001準拠インフラに保存</span>
            </div>
            <div class="trust-badge" role="listitem">
                <span class="trust-badge__icon" aria-hidden="true">👔</span>
                <span class="trust-badge__text">中小企業診断士監修｜最新の経営フレームワークでアルゴリズムを設計</span>
            </div>
            <div class="trust-badge" role="listitem">
                <span class="trust-badge__icon" aria-hidden="true">🤖</span>
                <span class="trust-badge__text">AIアシスタントがシナリオ比較と意思決定メモを自動生成</span>
            </div>
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
        st.markdown(
            """
            <div class=\"section-heading\" role=\"presentation\">
                <div class=\"section-heading__icon\" aria-hidden=\"true\"></div>
                <div>
                    <h2 class=\"section-heading__title\">現状サマリー</h2>
                    <p class=\"section-heading__subtitle\">最新の主要KPIで現状を俯瞰</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

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

    metric_cards = [
        MetricCard(
            icon="¥",
            label="売上高",
            value=format_amount_with_unit(amounts.get("REV", Decimal("0")), unit),
            description="チャネル×商品×月の年間売上合計",
            aria_label="年間売上高",
            assistive_text="売上高のカード。チャネル×商品×月の年間売上合計です。",
        ),
        MetricCard(
            icon="↗",
            label="粗利率",
            value=format_ratio(metrics.get("gross_margin")),
            description="粗利÷売上で算出される利益率",
            aria_label="粗利率",
            tone="positive" if (metrics.get("gross_margin") or Decimal("0")) >= Decimal("0.3") else "neutral",
            assistive_text="粗利率のカード。数値が高いほど利益体質が良好で、トーンバッジで状況を示しています。",
        ),
        MetricCard(
            icon="Σ",
            label="経常利益",
            value=format_amount_with_unit(amounts.get("ORD", Decimal("0")), unit),
            description="営業外収支も含めた利益水準",
            aria_label="経常利益の金額",
            assistive_text="経常利益のカード。営業外収支を含めた年間の利益水準です。",
        ),
        MetricCard(
            icon="⚑",
            label="損益分岐点売上高",
            value=format_amount_with_unit(metrics.get("breakeven"), unit),
            description="固定費を回収するために必要な売上高",
            aria_label="損益分岐点の売上高",
            tone="caution",
            assistive_text="損益分岐点売上高のカード。△バッジで注意が必要なことを示します。",
        ),
    ]
    render_metric_cards(metric_cards, grid_aria_label="主要指標サマリー")

    st.caption(f"FY{fiscal_year} 計画 ｜ 表示単位: {unit} ｜ FTE: {fte}")

    if not auth.is_authenticated():
        render_callout(
            icon="▣",
            title="ログインでセキュアなクラウド保存とバージョン管理を利用",
            body="ヘッダー右上の「ログイン」からアカウントを作成すると、暗号化ストレージに入力データを保存し、シナリオごとにバージョン履歴を管理できます。",
            tone="caution",
            aria_label="ログインを促す案内",
        )

    st.markdown(
        """
        <div class=\"section-heading\" role=\"presentation\">
            <div class=\"section-heading__icon\" aria-hidden=\"true\"></div>
            <div>
                <h2 class=\"section-heading__title\">次のステップ</h2>
                <p class=\"section-heading__subtitle\">ライトブルーの導線で操作手順を整理</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        1. **入力** ページで売上・原価・費用・投資・借入・税制を登録し、前提条件を整備する
        2. **分析** ページでPL/BS/CFとKPIを確認し、損益分岐点や資金繰りの健全性を評価する
        3. **シナリオ** ページで感度分析やシナリオ比較を行い、経営判断の優先順位を明確化する
        4. **レポート** ページでPDF / PowerPoint / Excel / Word を生成し、金融機関・投資家・社内会議へ展開する
        5. **設定** ページで単位や言語、セキュリティオプションなど既定値をカスタマイズする
        """
    )

    with tutorial_tab:
        st.markdown(
            """
            <div class=\"section-heading\" role=\"presentation\">
                <div class=\"section-heading__icon\" aria-hidden=\"true\"></div>
                <div>
                    <h2 class=\"section-heading__title\">チュートリアル</h2>
                    <p class=\"section-heading__subtitle\">主要な操作ポイントを簡潔に整理</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
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
