"""Reusable UI helpers for responsive cards and accessible controls."""
from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Sequence

import streamlit as st


@dataclass(frozen=True)
class MetricCard:
    icon: str
    label: str
    value: str
    description: str | None = None
    footnote: str | None = None
    trend: str | None = None
    aria_label: str | None = None
    tone: str | None = None  # e.g. "positive", "caution", "neutral"
    assistive_text: str | None = None


_TONE_BADGES: dict[str, tuple[str, str]] = {
    "positive": ("🟢", "好調"),
    "caution": ("⚠️", "注意"),
    "negative": ("🔴", "警戒"),
}


def render_metric_cards(cards: Sequence[MetricCard], *, grid_aria_label: str | None = None) -> None:
    """Render metric cards in a responsive grid that works on mobile/tablet."""

    if not cards:
        return
    card_blocks: list[str] = []
    for card in cards:
        aria_attr = f" aria-label=\"{html.escape(card.aria_label)}\"" if card.aria_label else ""
        tone_class = f" metric-card--{card.tone}" if card.tone else ""
        tone_badge = ""
        if card.tone and card.tone in _TONE_BADGES:
            badge_icon, badge_label = _TONE_BADGES[card.tone]
            tone_badge = (
                "<span class='metric-card__tone-badge' role='img' "
                f"aria-label='{html.escape(badge_label)}'>"
                f"{html.escape(badge_icon)}<span class='metric-card__tone-text'>{html.escape(badge_label)}</span>"
                "</span>"
            )
        description_html = (
            f"<p class='metric-card__description'>{html.escape(card.description)}</p>"
            if card.description
            else ""
        )
        footnote_html = (
            f"<p class='metric-card__footnote'>{html.escape(card.footnote)}</p>"
            if card.footnote
            else ""
        )
        trend_html = (
            f"<span class='metric-card__trend'>{html.escape(card.trend)}</span>"
            if card.trend
            else ""
        )
        assistive_html = (
            f"<span class='visually-hidden'>{html.escape(card.assistive_text)}</span>"
            if card.assistive_text
            else ""
        )
        block = (
            f"<section role='group'{aria_attr} class='metric-card{tone_class}'>"
            f"  <div class='metric-card__header'><span class='metric-card__icon'>{html.escape(card.icon)}</span>"
            f"  <span class='metric-card__label'>{html.escape(card.label)}</span>{trend_html}{tone_badge}</div>"
            f"  <p class='metric-card__value'>{html.escape(card.value)}</p>{assistive_html}"
            f"  {description_html}{footnote_html}"
            "</section>"
        )
        card_blocks.append(block)
    region_attrs = ""
    if grid_aria_label:
        region_attrs = f" role='region' aria-label='{html.escape(grid_aria_label)}' aria-live='polite'"
    grid_html = (
        f"<div class='responsive-card-grid'{region_attrs}>" + "".join(card_blocks) + "</div>"
    )
    st.markdown(grid_html, unsafe_allow_html=True)


def render_callout(*, icon: str, title: str, body: str, tone: str = "neutral", aria_label: str | None = None) -> None:
    aria_attr = f" aria-label=\"{html.escape(aria_label)}\"" if aria_label else ""
    st.markdown(
        """
        <div class="callout callout--{tone}" role="note"{aria_attr}>
            <span class="callout__icon">{icon}</span>
            <div class="callout__body">
                <strong class="callout__title">{title}</strong>
                <p>{body}</p>
            </div>
        </div>
        """.format(tone=html.escape(tone), icon=html.escape(icon), title=html.escape(title), body=html.escape(body), aria_attr=aria_attr),
        unsafe_allow_html=True,
    )


__all__ = ["MetricCard", "render_metric_cards", "render_callout"]
