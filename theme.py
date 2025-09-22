"""Centralised colour scheme, responsive layout tweaks and accessibility helpers."""
from __future__ import annotations

from typing import Dict

import streamlit as st

from services.security import enforce_https

THEME_COLORS: Dict[str, str] = {
    "background": "#F7F9FB",
    "surface": "#FFFFFF",
    "surface_alt": "#E8F1FA",
    "primary": "#1F4E79",
    "primary_light": "#4F83B3",
    "accent": "#F2C57C",
    "positive": "#3A7D44",
    "positive_strong": "#14532D",
    "negative": "#C2410C",
    "neutral": "#CBD5F5",
    "text": "#1F2A37",
    "text_subtle": "#4B5563",
    "chart_blue": "#1f77b4",
    "chart_orange": "#ff7f0e",
    "chart_green": "#2ca02c",
    "chart_purple": "#9467bd",
}

DARK_THEME_COLORS: Dict[str, str] = {
    "background": "#0F172A",
    "surface": "#1E293B",
    "surface_alt": "#24324D",
    "primary": "#60A5FA",
    "primary_light": "#93C5FD",
    "accent": "#FBBF24",
    "positive": "#34D399",
    "positive_strong": "#059669",
    "negative": "#F87171",
    "neutral": "#64748B",
    "text": "#F9FAFB",
    "text_subtle": "#E2E8F0",
    "chart_blue": "#60A5FA",
    "chart_orange": "#F59E0B",
    "chart_green": "#4ADE80",
    "chart_purple": "#C4B5FD",
}

COLOR_BLIND_COLORS: Dict[str, str] = {
    "background": "#F8FAFC",
    "surface": "#FFFFFF",
    "surface_alt": "#E2E8F0",
    "primary": "#205493",
    "primary_light": "#2F74C8",
    "accent": "#F0B429",
    "positive": "#2E8540",
    "positive_strong": "#1B512D",
    "negative": "#B94700",
    "neutral": "#CBD5E1",
    "text": "#1F2933",
    "text_subtle": "#52606D",
    "chart_blue": "#0173B2",
    "chart_orange": "#DE8F05",
    "chart_green": "#029E73",
    "chart_purple": "#CC78BC",
}

HIGH_CONTRAST_COLORS: Dict[str, str] = {
    "background": "#0F172A",
    "surface": "#111827",
    "surface_alt": "#1F2937",
    "primary": "#F97316",
    "primary_light": "#FB923C",
    "accent": "#FACC15",
    "positive": "#22C55E",
    "positive_strong": "#16A34A",
    "negative": "#F87171",
    "neutral": "#94A3B8",
    "text": "#F9FAFB",
    "text_subtle": "#E2E8F0",
    "chart_blue": "#60A5FA",
    "chart_orange": "#FDBA74",
    "chart_green": "#86EFAC",
    "chart_purple": "#C4B5FD",
}

CUSTOM_STYLE_TEMPLATE = """
<style>
:root {{
    --base-font-scale: {font_scale};
    --base-bg: {background};
    --surface: {surface};
    --surface-alt: {surface_alt};
    --primary: {primary};
    --primary-light: {primary_light};
    --accent: {accent};
    --positive: {positive};
    --positive-strong: {positive_strong};
    --negative: {negative};
    --neutral: {neutral};
    --text-color: {text};
    --text-subtle: {text_subtle};
    --chart-blue: {chart_blue};
    --chart-orange: {chart_orange};
    --chart-green: {chart_green};
    --chart-purple: {chart_purple};
    --sidebar-compact: {sidebar_compact};
}}

html, body, [data-testid="stAppViewContainer"] {{
    background-color: var(--base-bg);
    color: var(--text-color);
    font-family: "Noto Sans JP", "Hiragino Sans", "Yu Gothic", sans-serif;
    font-size: calc(16px * var(--base-font-scale));
    line-height: 1.6;
}}

[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, var(--primary) 0%, var(--primary-light) 100%);
    color: #F7FAFC;
    width: calc(18rem - 9rem * var(--sidebar-compact));
    min-width: calc(16rem - 8rem * var(--sidebar-compact));
    transition: width 0.35s ease;
}}

[data-testid="stSidebar"] * {{
    color: #F7FAFC !important;
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] ul {{
    padding: 0.6rem 0.25rem 1.2rem 0.25rem;
    display: grid;
    gap: 0.25rem;
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a {{
    display: flex;
    align-items: center;
    gap: calc(0.75rem * (1 - var(--sidebar-compact)) + 0.35rem);
    padding: 0.55rem 0.9rem;
    border-radius: 12px;
    transition: background-color 0.25s ease, gap 0.2s ease;
    font-weight: 600;
    position: relative;
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover {{
    background-color: rgba(255, 255, 255, 0.14);
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a::before {{
    font-size: 1.25rem;
    margin-right: calc(0.35rem * (1 - var(--sidebar-compact)));
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] span {{
    opacity: calc(1 - 0.92 * var(--sidebar-compact));
    transition: opacity 0.25s ease;
    white-space: nowrap;
    pointer-events: none;
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Home"]::before {{
    content: "🏠";
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Inputs"]::before {{
    content: "🧾";
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Analysis"]::before {{
    content: "📊";
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Scenarios"]::before {{
    content: "🧮";
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Report"]::before {{
    content: "📄";
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Settings"]::before {{
    content: "⚙️";
}}

[data-testid="stSidebar"] button:focus-visible,
button:focus-visible {{
    outline: 3px solid var(--accent) !important;
    outline-offset: 2px;
}}

[data-testid="stAppViewContainer"] a {{
    color: var(--primary);
    text-decoration: underline;
    text-decoration-thickness: 0.12em;
}}

.stTabs [role="tablist"] {{
    gap: 0.4rem;
    border-bottom: 1px solid var(--neutral);
    flex-wrap: wrap;
}}

.stTabs [role="tab"] {{
    font-weight: 600;
    padding: 0.75rem 1.2rem;
    border-radius: 14px 14px 0 0;
    background-color: transparent;
    color: var(--text-subtle);
}}

.stTabs [role="tab"][aria-selected="true"] {{
    background-color: var(--surface);
    color: var(--primary);
    box-shadow: 0 -2px 20px rgba(31, 78, 121, 0.08);
    border-bottom: 3px solid var(--accent);
}}

.hero-card {{
    background: linear-gradient(135deg, rgba(93, 169, 233, 0.92) 0%, rgba(112, 169, 161, 0.92) 100%);
    color: #ffffff;
    padding: 2.2rem 2.8rem;
    border-radius: 26px;
    box-shadow: 0 24px 48px rgba(22, 60, 90, 0.25);
    margin-bottom: 1.5rem;
}}

.hero-card h1 {{
    margin: 0 0 0.6rem 0;
    font-size: calc(2.1rem * var(--base-font-scale));
    font-weight: 700;
}}

.hero-card p {{
    margin: 0;
    font-size: calc(1.02rem * var(--base-font-scale));
    opacity: 0.92;
}}

.responsive-card-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 1rem;
    width: 100%;
}}

.metric-card {{
    background: linear-gradient(145deg, var(--surface) 0%, var(--surface-alt) 100%);
    border-radius: 20px;
    padding: 1.2rem 1.4rem;
    box-shadow: 0 18px 28px rgba(31, 78, 121, 0.08);
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
}}

.metric-card--positive {{
    border: 2px solid var(--positive);
}}

.metric-card--caution {{
    border: 2px solid var(--accent);
}}

.metric-card--negative {{
    border: 2px solid var(--negative);
}}

.metric-card__header {{
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: calc(0.95rem * var(--base-font-scale));
    color: var(--text-subtle);
}}

.metric-card__icon {{
    font-size: 1.3rem;
}}

.metric-card__label {{
    font-weight: 600;
}}

.metric-card__trend {{
    margin-left: auto;
    font-size: calc(0.82rem * var(--base-font-scale));
    font-weight: 600;
}}

.metric-card__tone-badge {{
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    margin-left: 0.5rem;
    padding: 0.1rem 0.5rem;
    border-radius: 999px;
    background: rgba(31, 78, 121, 0.12);
    font-size: calc(0.75rem * var(--base-font-scale));
}}
.metric-card__tone-text {{
    font-weight: 600;
    letter-spacing: 0.02em;
}}
.metric-card__value {{
    font-size: calc(1.5rem * var(--base-font-scale));
    font-weight: 700;
    color: var(--primary);
    margin: 0;
}}

.metric-card__description {{
    margin: 0;
    font-size: calc(0.9rem * var(--base-font-scale));
    color: var(--text-subtle);
}}

.metric-card__footnote {{
    margin: 0;
    font-size: calc(0.8rem * var(--base-font-scale));
    color: var(--text-subtle);
}}

.callout {{
    display: flex;
    gap: 0.8rem;
    padding: 1rem 1.1rem;
    border-radius: 16px;
    margin-bottom: 1rem;
    background-color: var(--surface);
    border-left: 6px solid var(--primary);
    box-shadow: 0 12px 18px rgba(31, 78, 121, 0.08);
}}

.callout--positive {{
    border-left-color: var(--positive);
}}

.callout--caution {{
    border-left-color: var(--accent);
}}

.callout__icon {{
    font-size: 1.5rem;
}}

.callout__title {{
    font-size: calc(1rem * var(--base-font-scale));
    color: var(--primary);
}}

.callout__body p {{
    margin: 0;
    font-size: calc(0.92rem * var(--base-font-scale));
}}

.wizard-checklist {
    display: grid;
    gap: 0.35rem;
    padding: 0.4rem 0;
}

.wizard-checklist__item {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: calc(0.92rem * var(--base-font-scale));
}

.visually-hidden {{
    position: absolute !important;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
}}
[data-testid="stMetric"] {{
    background: linear-gradient(135deg, var(--surface) 0%, var(--surface-alt) 100%);
    border-radius: 18px;
    padding: 1rem 1.2rem;
    box-shadow: 0 14px 28px rgba(31, 78, 121, 0.08);
}}

[data-testid="stMetric"] [data-testid="stMetricLabel"] {{
    font-size: calc(0.92rem * var(--base-font-scale));
    color: var(--text-subtle);
}}

[data-testid="stMetric"] [data-testid="stMetricValue"] {{
    color: var(--primary);
    font-weight: 700;
    font-size: calc(1.35rem * var(--base-font-scale));
}}

[data-testid="stDataFrame"] {{
    background-color: var(--surface);
    border-radius: 18px;
    padding: 0.6rem 0.8rem 0.9rem 0.8rem;
    box-shadow: 0 12px 26px rgba(31, 78, 121, 0.06);
}}

button[kind="primary"] {{
    background-color: var(--primary);
    border-radius: 999px;
    border: none;
    box-shadow: 0 10px 20px rgba(31, 78, 121, 0.15);
}}

button[kind="primary"]:hover {{
    background-color: var(--primary-light);
}}

button[kind="primary"]:focus-visible {{
    outline: 3px solid var(--accent) !important;
    outline-offset: 2px;
}}

.field-error {{
    border: 1px solid var(--negative);
    border-radius: 12px;
    padding: 0.8rem;
    background-color: rgba(248, 113, 113, 0.15);
    color: var(--negative);
}}

@media (max-width: 980px) {{
    .hero-card {{
        padding: 1.6rem 1.8rem;
    }}
    .responsive-card-grid {{
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    }}
    [data-testid="stSidebar"] {{
        width: calc(17rem - 9rem * var(--sidebar-compact));
    }}
}}

@media (max-width: 640px) {{
    .hero-card h1 {{
        font-size: calc(1.6rem * var(--base-font-scale));
    }}
    .hero-card p {{
        font-size: calc(0.95rem * var(--base-font-scale));
    }}
    .stTabs [role="tab"] {{
        padding: 0.6rem 0.9rem;
    }}
    .metric-card {{
        padding: 1rem 1.1rem;
    }}
    .responsive-card-grid {{
        grid-template-columns: 1fr;
    }}
    [data-testid="stSidebar"] {{
        width: calc(16rem - 10rem * var(--sidebar-compact));
    }}
}}

@media (prefers-reduced-motion: reduce) {{
    *, *::before, *::after {{
        transition-duration: 0.001ms !important;
        animation-duration: 0.001ms !important;
    }}
}}
</style>
"""


def _clamp_font_scale(value: float) -> float:
    return max(0.85, min(1.4, value))


def _resolve_palette(*, color_scheme: str, high_contrast: bool, color_blind: bool) -> Dict[str, str]:
    if high_contrast:
        return HIGH_CONTRAST_COLORS
    if color_scheme == "dark":
        return DARK_THEME_COLORS
    if color_blind:
        return COLOR_BLIND_COLORS
    return THEME_COLORS


def build_custom_style(
    *,
    font_scale: float = 1.0,
    high_contrast: bool = False,
    color_scheme: str = "light",
    color_blind: bool = False,
    sidebar_compact: bool = False,
) -> str:
    palette = _resolve_palette(
        color_scheme=color_scheme,
        high_contrast=high_contrast,
        color_blind=color_blind,
    )
    return CUSTOM_STYLE_TEMPLATE.format(
        font_scale=f"{_clamp_font_scale(font_scale):.2f}",
        sidebar_compact="1" if sidebar_compact else "0",
        **palette,
    )


def inject_theme() -> None:
    """Apply the shared CSS theme to the current page."""

    font_scale = float(st.session_state.get("ui_font_scale", 1.0))
    high_contrast = bool(st.session_state.get("ui_high_contrast", False))
    color_scheme = str(st.session_state.get("ui_color_scheme", "light"))
    color_blind = bool(st.session_state.get("ui_color_blind", False))
    sidebar_compact = bool(st.session_state.get("ui_sidebar_compact", False))
    st.markdown(
        build_custom_style(
            font_scale=font_scale,
            high_contrast=high_contrast,
            color_scheme=color_scheme,
            color_blind=color_blind,
            sidebar_compact=sidebar_compact,
        ),
        unsafe_allow_html=True,
    )
    enforce_https()


__all__ = [
    "THEME_COLORS",
    "HIGH_CONTRAST_COLORS",
    "DARK_THEME_COLORS",
    "COLOR_BLIND_COLORS",
    "build_custom_style",
    "inject_theme",
]
