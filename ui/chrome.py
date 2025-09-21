"""Shared UI chrome elements (header, footer, help tools)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import streamlit as st

USAGE_GUIDE_TEXT = (
    "1. **入力を整える**: コントロールハブで売上・コストのレバーと会計年度、FTEを設定します。\n"
    "2. **検証と分析**: シナリオ/感応度タブで前提を比較し、AIインサイトでチェックポイントを確認します。\n"
    "3. **可視化と出力**: グラフや表で可視化し、エクスポートタブからExcelをダウンロードして共有します。"
)


@dataclass(frozen=True)
class HeaderActions:
    """User interactions emitted from the global header."""

    toggled_help: bool = False
    reset_requested: bool = False


def render_app_header(
    *,
    title: str,
    subtitle: str,
    help_key: str = "show_usage_guide",
    help_button_label: str = "使い方ガイド",
    reset_label: str = "Reset all",
    show_reset: bool = True,
    on_reset: Callable[[], None] | None = None,
) -> HeaderActions:
    """Render the global header with help and reset controls."""

    toggled_help = False
    reset_requested = False

    with st.container():
        columns = st.columns([4, 1, 1] if show_reset else [4, 1], gap="large")
        with columns[0]:
            st.title(title)
            st.caption(subtitle)
        help_col = columns[1]
        with help_col:
            if st.button(
                help_button_label,
                use_container_width=True,
                key=f"{help_key}_toggle_button",
            ):
                toggled_help = True
        if show_reset:
            reset_col = columns[2]
            with reset_col:
                if st.button(
                    reset_label,
                    use_container_width=True,
                    key="app_reset_all_button",
                    help="入力値と分析結果を初期状態に戻します。",
                ):
                    reset_requested = True
                    if on_reset is not None:
                        on_reset()

    return HeaderActions(toggled_help=toggled_help, reset_requested=reset_requested)


def render_usage_guide_panel(help_key: str = "show_usage_guide") -> None:
    """Display the collapsible usage guide when the toggle is active."""

    placeholder = st.container()
    if st.session_state.get(help_key):
        with placeholder.expander("3ステップ活用ガイド", expanded=True):
            st.markdown(USAGE_GUIDE_TEXT)


def render_app_footer(
    caption: str = "© 経営計画策定WEBアプリ（Streamlit版） | 表示単位と計算単位を分離し、丸めの影響を最小化しています。",
) -> None:
    """Render the global footer."""

    st.divider()
    st.caption(caption)


__all__ = [
    "HeaderActions",
    "render_app_footer",
    "render_app_header",
    "render_usage_guide_panel",
]
