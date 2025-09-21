"""Centralised colour scheme and style helpers."""
from __future__ import annotations

from typing import Dict

import streamlit as st

THEME_COLORS: Dict[str, str] = {
    "background": "#F7F9FB",
    "surface": "#FFFFFF",
    "surface_alt": "#E8F1FA",
    "primary": "#1F4E79",
    "primary_light": "#4F83B3",
    "accent": "#F2C57C",
    "positive": "#70A9A1",
    "positive_strong": "#2B7A78",
    "negative": "#F28F8F",
    "neutral": "#C2D3E5",
    "text": "#203040",
    "text_subtle": "#596B7A",
}

CUSTOM_STYLE = f"""
<style>
:root {{
    --base-bg: {THEME_COLORS["background"]};
    --surface: {THEME_COLORS["surface"]};
    --surface-alt: {THEME_COLORS["surface_alt"]};
    --primary: {THEME_COLORS["primary"]};
    --primary-light: {THEME_COLORS["primary_light"]};
    --accent: {THEME_COLORS["accent"]};
    --positive: {THEME_COLORS["positive"]};
    --positive-strong: {THEME_COLORS["positive_strong"]};
    --negative: {THEME_COLORS["negative"]};
    --neutral: {THEME_COLORS["neutral"]};
    --text-color: {THEME_COLORS["text"]};
    --text-subtle: {THEME_COLORS["text_subtle"]};
}}

html, body, [data-testid="stAppViewContainer"] {{
    background-color: var(--base-bg);
    color: var(--text-color);
    font-family: "Noto Sans JP", "Hiragino Sans", "Yu Gothic", sans-serif;
}}

[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, var(--primary) 0%, var(--primary-light) 100%);
    color: #F7FAFC;
}}

[data-testid="stSidebar"] * {{
    color: #F7FAFC !important;
}}

.stTabs [role="tablist"] {{
    gap: 0.4rem;
    border-bottom: 1px solid var(--neutral);
}}

.stTabs [role="tab"] {{
    font-weight: 600;
    padding: 0.85rem 1.4rem;
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

div[data-testid="stMetric"] {{
    background: linear-gradient(135deg, var(--surface) 0%, var(--surface-alt) 100%);
    border-radius: 18px;
    padding: 1.15rem 1.3rem;
    box-shadow: 0 14px 28px rgba(31, 78, 121, 0.08);
    backdrop-filter: blur(6px);
}}

div[data-testid="stMetric"] [data-testid="stMetricLabel"] {{
    font-size: 0.92rem;
    color: var(--text-subtle);
}}

div[data-testid="stMetric"] [data-testid="stMetricValue"] {{
    color: var(--primary);
    font-weight: 700;
}}

div[data-testid="stMetric"] [data-testid="stMetricDelta"] {{
    color: var(--accent) !important;
}}

div[data-testid="stDataFrame"] {{
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
    font-size: 2.35rem;
    font-weight: 700;
}}

.hero-card p {{
    margin: 0;
    font-size: 1.08rem;
    opacity: 0.92;
}}

.insight-card {{
    background-color: var(--surface);
    border-radius: 18px;
    padding: 1.1rem 1.3rem;
    box-shadow: 0 12px 24px rgba(31, 78, 121, 0.08);
    border-left: 6px solid var(--primary-light);
    margin-bottom: 1rem;
}}

.insight-card.positive {{
    border-left-color: var(--positive);
}}

.insight-card.warning {{
    border-left-color: var(--accent);
}}

.insight-card.alert {{
    border-left-color: var(--negative);
}}

.insight-card h4 {{
    margin: 0 0 0.4rem 0;
    font-size: 1.05rem;
    color: var(--primary);
}}

.insight-card p {{
    margin: 0;
    font-size: 0.95rem;
    color: var(--text-subtle);
    line-height: 1.55;
}}

.anomaly-table caption {{
    caption-side: top;
    font-weight: 600;
    color: var(--primary);
}}

.ai-badge {{
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    background-color: rgba(112, 169, 161, 0.16);
    color: var(--positive-strong);
    border-radius: 999px;
    padding: 0.35rem 0.9rem;
    font-weight: 600;
    letter-spacing: 0.02em;
}}

.field-error {{
    border: 1px solid {THEME_COLORS["negative"]};
    border-radius: 12px;
    padding: 0.8rem;
    background-color: rgba(242, 143, 143, 0.12);
    color: {THEME_COLORS["negative"]};
}}
</style>
"""


def inject_theme() -> None:
    """Apply the shared CSS theme to the current page."""

    st.markdown(CUSTOM_STYLE, unsafe_allow_html=True)


__all__ = ["THEME_COLORS", "CUSTOM_STYLE", "inject_theme"]
