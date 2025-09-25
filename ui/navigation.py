"""Custom global navigation and workflow banner components."""
from __future__ import annotations

from dataclasses import dataclass
import textwrap
import streamlit as st


@dataclass(frozen=True)
class NavigationItem:
    """Metadata for a sidebar navigation entry."""

    key: str
    label: str
    icon: str
    description: str
    page_path: str | None
    step_label: str
    include_in_flow: bool = True


NAVIGATION_ITEMS: tuple[NavigationItem, ...] = (
    NavigationItem(
        key="home",
        label="ホーム",
        icon="🏠",
        description="主要KPIとインサイトを確認するダッシュボードへ移動します。",
        page_path="pages/00_Home.py",
        step_label="①ホーム",
        include_in_flow=False,
    ),
    NavigationItem(
        key="inputs",
        label="入力",
        icon="📝",
        description="3C分析やビジネスモデルキャンバスなどの前提条件を入力します。",
        page_path="pages/10_Inputs.py",
        step_label="②データ入力",
    ),
    NavigationItem(
        key="analysis",
        label="分析",
        icon="📊",
        description="KPIダッシュボードや損益分岐・キャッシュフロー分析を実行します。",
        page_path="pages/20_Analysis.py",
        step_label="③分析",
    ),
    NavigationItem(
        key="scenarios",
        label="シナリオ",
        icon="🔀",
        description="ベースライン/ベスト/ワーストを比較し、VaRやDSCR閾値を確認します。",
        page_path="pages/30_Scenarios.py",
        step_label="④シナリオ",
    ),
    NavigationItem(
        key="report",
        label="レポート",
        icon="📄",
        description="McKinsey風テンプレートでPDF・PPTX・Excel・Wordへ出力します。",
        page_path="pages/40_Report.py",
        step_label="⑤レポート",
    ),
    NavigationItem(
        key="settings",
        label="設定",
        icon="⚙️",
        description="単位・会計期間・バックアップ設定を編集します。",
        page_path="pages/90_Settings.py",
        step_label="設定",
        include_in_flow=False,
    ),
)


WORKFLOW_ITEMS: tuple[NavigationItem, ...] = tuple(
    item for item in NAVIGATION_ITEMS if item.include_in_flow
)


def _switch_to(page_path: str | None) -> None:
    """Navigate to the given multipage *page_path* if provided."""

    if not page_path:
        return
    st.switch_page(page_path)


def render_global_navigation(current_key: str) -> None:
    """Render labelled sidebar navigation with icon buttons and tooltips."""

    st.sidebar.markdown(
        "<div class='sidebar-nav__header'>ワークフローナビゲーション</div>",
        unsafe_allow_html=True,
    )

    nav_container = st.sidebar.container()
    with nav_container:
        st.markdown("<div class='sidebar-nav' role='navigation'>", unsafe_allow_html=True)
        for item in NAVIGATION_ITEMS:
            is_active = item.key == current_key
            if is_active:
                st.session_state["sidebar_step"] = item.step_label
            clicked = st.button(
                f"{item.icon} {item.label}",
                key=f"nav_button_{item.key}",
                help=item.description,
                use_container_width=True,
                type="primary" if is_active else "secondary",
                disabled=is_active,
            )
            if clicked and not is_active:
                st.session_state["sidebar_step"] = item.step_label
                _switch_to(item.page_path)
        st.markdown("</div>", unsafe_allow_html=True)

    st.sidebar.caption("入力→分析→シナリオ→レポートの順に進めると迷わず作業できます。")


def render_workflow_banner(current_key: str) -> None:
    """Render a sticky top workflow banner indicating the current phase."""

    if not WORKFLOW_ITEMS:
        return

    current_index = next(
        (idx for idx, item in enumerate(WORKFLOW_ITEMS) if item.key == current_key),
        None,
    )
    if current_index is None:
        current_index = 0 if current_key == "home" else len(WORKFLOW_ITEMS) - 1

    fragments: list[str] = []
    for idx, item in enumerate(WORKFLOW_ITEMS):
        status = "completed" if idx < current_index else "upcoming"
        if idx == current_index:
            status = "current"
        aria_current = " aria-current=\"step\"" if status == "current" else ""
        fragments.append(
            textwrap.dedent(
                """
                <li class='workflow-banner__item workflow-banner__item--{status}'{aria_current}>
                  <span class='workflow-banner__badge'>{badge}</span>
                  <div class='workflow-banner__label'>
                    <span class='workflow-banner__label-text'>{icon} {label}</span>
                    <span class='workflow-banner__description'>{desc}</span>
                  </div>
                </li>
                """
            ).format(
                status=status,
                aria_current=aria_current,
                badge=f"{idx + 1:02d}",
                icon=item.icon,
                label=item.label,
                desc=item.description,
            )
        )

    if current_key == "home":
        next_step_text = WORKFLOW_ITEMS[0].label
    elif current_index >= len(WORKFLOW_ITEMS) - 1:
        next_step_text = "完了です"
    else:
        next_step_text = WORKFLOW_ITEMS[current_index + 1].label

    banner_html = textwrap.dedent(
        """
        <section class='workflow-banner' aria-label='ユーザージャーニー'>
          <header class='workflow-banner__title'>入力からレポートまでの進行状況</header>
          <ol class='workflow-banner__list'>
            {items}
          </ol>
          <div class='workflow-banner__meta'>次のステップ: {next_step}</div>
        </section>
        """
    ).format(items="".join(fragments), next_step=next_step_text)

    st.markdown(banner_html, unsafe_allow_html=True)

