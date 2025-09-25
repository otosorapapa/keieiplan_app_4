"""Shared UI chrome elements (header, footer, help tools)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import html

import streamlit as st
from services import auth
from services.auth import AuthError
from ui.streamlit_compat import rerun, use_container_width_kwargs

USAGE_GUIDE_TEXT = (
    "1. **入力を整える**: コントロールハブで売上・コストのレバーと会計年度、FTEを設定します。\n"
    "2. **検証と分析**: シナリオ/感応度タブで前提を比較し、AIインサイトでチェックポイントを確認します。\n"
    "3. **可視化と出力**: グラフや表で可視化し、PDF / PowerPoint / Excel / Wordをエクスポートして共有します。"
)


@dataclass(frozen=True)
class HeaderActions:
    """User interactions emitted from the global header."""

    toggled_help: bool = False
    reset_requested: bool = False
    logout_requested: bool = False


def render_app_header(
    *,
    title: str,
    subtitle: str,
    help_key: str = "show_usage_guide",
    help_button_label: str = "操作ガイド",
    reset_label: str = "全データをリセット",
    show_reset: bool = True,
    on_reset: Callable[[], None] | None = None,
) -> HeaderActions:
    """Render the global header with help and reset controls."""

    toggled_help = False
    reset_requested = False
    logout_requested = False

    with st.container():
        column_spec = [4, 1.2, 1.1, 1.4, 1.2] if show_reset else [4, 1.2, 1.1, 1.4]
        columns = st.columns(column_spec, gap="large")
        with columns[0]:
            st.title(title)
            st.caption(subtitle)
        help_col = columns[1]
        with help_col:
            if st.button(
                help_button_label,
                key=f"{help_key}_toggle_button",
                **use_container_width_kwargs(st.button),
            ):
                toggled_help = True
        accessibility_col = columns[2]
        with accessibility_col:
            with st.popover(
                "Aa 表示カスタマイズ",
                help="フォントサイズや配色を調整して読みやすさを最適化します。",
            ):
                st.write("読みやすさを調整")
                st.slider(
                    "フォント倍率",
                    min_value=0.9,
                    max_value=1.3,
                    step=0.05,
                    value=float(st.session_state.get("ui_font_scale", 1.0)),
                    key="ui_font_scale",
                    help="画面全体の文字サイズを変更してデバイスに合わせた表示にします。",
                )
                st.toggle(
                    "高コントラストモード",
                    value=bool(st.session_state.get("ui_high_contrast", False)),
                    key="ui_high_contrast",
                    help="色のコントラストを強めて視認性を高めます。",
                )
                st.radio(
                    "テーマ",
                    options=["light", "dark"],
                    index=0 if st.session_state.get("ui_color_scheme", "light") == "light" else 1,
                    format_func=lambda value: "ライト" if value == "light" else "ダーク",
                    key="ui_color_scheme",
                    help="閲覧環境に合わせてライト/ダークテーマを切り替えます。",
                )
                st.toggle(
                    "色覚サポート",
                    value=bool(st.session_state.get("ui_color_blind", False)),
                    key="ui_color_blind",
                    help="色覚特性に配慮したパレットへ変更します。",
                )
                st.toggle(
                    "サイドバーをコンパクト表示",
                    value=bool(st.session_state.get("ui_sidebar_compact", False)),
                    key="ui_sidebar_compact",
                    help="左メニューをアイコン中心にして作業領域を広げます。",
                )
                st.toggle(
                    "チュートリアルモード",
                    value=bool(st.session_state.get("tutorial_mode", True)),
                    key="tutorial_mode",
                    help="有効にすると各ステップで操作ガイドがポップアップ表示されます。",
                )
                st.caption("設定は全ページで共有されます。")
        account_col = columns[3]
        with account_col:
            current_user = auth.get_current_user()
            account_label = (
                f"▣ {current_user.display_name}" if current_user else "⎔ ログイン"
            )
            with st.popover(account_label, help="暗号化されたクラウド保存とバージョン管理を利用するにはログインしてください。"):
                if current_user:
                    st.markdown(
                        f"**{current_user.display_name}**\n\n{current_user.email}",
                    )
                    st.caption("役割: " + ("管理者" if current_user.role == "admin" else "メンバー"))
                    if st.button("ログアウト", key="header_logout_button", help="セキュアにセッションを終了します。"):
                        auth.logout_user()
                        st.toast("ログアウトしました。", icon="◇")
                        logout_requested = True
                        rerun()
                else:
                    login_tab, register_tab = st.tabs(["ログイン", "新規登録"])
                    with login_tab:
                        with st.form("header_login_form"):
                            login_email = st.text_input(
                                "メールアドレス",
                                key="header_login_email",
                                placeholder="user@example.com",
                            )
                            login_password = st.text_input(
                                "パスワード",
                                key="header_login_password",
                                type="password",
                            )
                            if st.form_submit_button("ログイン"):
                                try:
                                    auth.login_user(login_email, login_password)
                                    st.success("ログインしました。ページを更新します。")
                                    rerun()
                                except AuthError as exc:
                                    st.error(str(exc))
                    with register_tab:
                        with st.form("header_register_form"):
                            register_name = st.text_input(
                                "表示名",
                                key="header_register_name",
                                placeholder="例：山田 太郎",
                            )
                            register_email = st.text_input(
                                "メールアドレス",
                                key="header_register_email",
                                placeholder="user@example.com",
                            )
                            register_password = st.text_input(
                                "パスワード",
                                key="header_register_password",
                                type="password",
                                help="英数字と記号を組み合わせると安全性が高まります。",
                            )
                            if st.form_submit_button("アカウントを作成"):
                                try:
                                    user = auth.register_user(
                                        email=register_email,
                                        password=register_password,
                                        display_name=register_name or register_email,
                                    )
                                    auth.login_via_token(user)
                                    st.success("アカウントを作成しました。ページを更新します。")
                                    rerun()
                                except AuthError as exc:
                                    st.error(str(exc))
        if show_reset:
            reset_col = columns[4]
            with reset_col:
                if st.button(
                    reset_label,
                    key="app_reset_all_button",
                    help="入力値と分析結果を初期状態に戻します。",
                    **use_container_width_kwargs(st.button),
                ):
                    reset_requested = True
                    if on_reset is not None:
                        on_reset()

    return HeaderActions(
        toggled_help=toggled_help,
        reset_requested=reset_requested,
        logout_requested=logout_requested,
    )


def render_usage_guide_panel(help_key: str = "show_usage_guide") -> None:
    """Display the collapsible usage guide when the toggle is active."""

    placeholder = st.container()
    if st.session_state.get(help_key):
        with placeholder.expander("3ステップ活用ガイド", expanded=True):
            st.markdown(USAGE_GUIDE_TEXT)


def render_app_footer(
    caption: str = "© 経営計画スタジオ | 情報設計の最適化と精緻な財務モデリングを提供します。",
) -> None:
    """Render the global footer."""

    st.divider()
    safe_caption = html.escape(caption)
    st.markdown(
        """
        <footer class="app-footer" role="contentinfo">
            <div class="app-footer__brand">
                <span class="app-footer__logo" aria-hidden="true">▥</span>
                <div>
                    <span class="app-footer__brand-name">経営計画スタジオ</span>
                    <span class="app-footer__tagline">Powered by AI & Consulting</span>
                </div>
            </div>
            <div class="app-footer__trust">
                <div class="app-footer__security">
                    <span class="security-badge" aria-label="ISO/IEC 27001認証">🔐 ISO/IEC 27001</span>
                    <span class="security-badge" aria-label="SSL/TLS暗号化">🔒 SSL/TLS</span>
                </div>
                <p class="app-footer__security-text">データは暗号化され、ISO/IEC 27001に準拠したストレージに保管されています。</p>
            </div>
            <div class="app-footer__expertise" role="list" aria-label="専門家監修に関するバッジ">
                <span class="expert-badge" role="listitem">中小企業診断士が監修</span>
                <span class="expert-badge" role="listitem">最新の経営フレームワークに準拠</span>
            </div>
            <div class="app-footer__links">
                <a href="mailto:support@keieiplan.jp">サポートに連絡</a>
                <span aria-hidden="true">／</span>
                <a href="https://keieiplan.jp/policy" target="_blank" rel="noopener noreferrer">利用規約</a>
            </div>
            <p class="app-footer__caption">{caption}</p>
        </footer>
        """.format(caption=safe_caption),
        unsafe_allow_html=True,
    )


__all__ = [
    "HeaderActions",
    "render_app_footer",
    "render_app_header",
    "render_usage_guide_panel",
]
