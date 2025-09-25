"""Centralised colour scheme, responsive layout tweaks and accessibility helpers."""
from __future__ import annotations

from typing import Dict

import streamlit as st

from services.security import enforce_https

THEME_COLORS: Dict[str, str] = {
    "background": "#F7F8FA",
    "surface": "#FFFFFF",
    "surface_alt": "#EEF1F6",
    "primary": "#0B1F3B",
    "primary_light": "#1E3553",
    "accent": "#1E88E5",
    "positive": "#3C7A5E",
    "positive_strong": "#2F5F4A",
    "negative": "#B5504A",
    "neutral": "#D3DAE3",
    "text": "#1A1A1A",
    "text_subtle": "#5A6B7A",
    "chart_blue": "#1E88E5",
    "chart_orange": "#5E9ED6",
    "chart_green": "#3C7A5E",
    "chart_purple": "#6F7FA3",
    "warning": "#B27B16",
}

DARK_THEME_COLORS: Dict[str, str] = {
    "background": "#071223",
    "surface": "#0F1D33",
    "surface_alt": "#16263D",
    "primary": "#1E88E5",
    "primary_light": "#4FA0E9",
    "accent": "#6AB2F2",
    "positive": "#5FAF93",
    "positive_strong": "#3E7F68",
    "negative": "#D06A6A",
    "neutral": "#3E4C63",
    "text": "#F1F4F9",
    "text_subtle": "#C6CFDB",
    "chart_blue": "#6AB2F2",
    "chart_orange": "#84C1F2",
    "chart_green": "#5FAF93",
    "chart_purple": "#A0BFE9",
    "warning": "#E0B565",
}

COLOR_BLIND_COLORS: Dict[str, str] = {
    "background": "#F7F8FA",
    "surface": "#FFFFFF",
    "surface_alt": "#EEF1F6",
    "primary": "#0B1F3B",
    "primary_light": "#1E395A",
    "accent": "#1170AA",
    "positive": "#4C7C6A",
    "positive_strong": "#366054",
    "negative": "#B45A4C",
    "neutral": "#D0D6E0",
    "text": "#1A1A1A",
    "text_subtle": "#566472",
    "chart_blue": "#1170AA",
    "chart_orange": "#5B8E95",
    "chart_green": "#6A7BA3",
    "chart_purple": "#8A89A8",
    "warning": "#AF7F2E",
}

HIGH_CONTRAST_COLORS: Dict[str, str] = {
    "background": "#FFFFFF",
    "surface": "#EFF3F9",
    "surface_alt": "#E0E7F1",
    "primary": "#0B1F3B",
    "primary_light": "#1E88E5",
    "accent": "#000000",
    "positive": "#005C3C",
    "positive_strong": "#003F29",
    "negative": "#7A1F27",
    "neutral": "#4A5C73",
    "text": "#000000",
    "text_subtle": "#1A1A1A",
    "chart_blue": "#0B1F3B",
    "chart_orange": "#1E88E5",
    "chart_green": "#005C3C",
    "chart_purple": "#2F3E72",
    "warning": "#8C4A00",
}

CUSTOM_STYLE_TEMPLATE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Source+Sans+3:wght@400;500;600;700&display=swap');

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
    --warning: {warning};
    --border-color: rgba(11, 31, 59, 0.12);
    --border-strong: rgba(11, 31, 59, 0.2);
    --shadow-soft: 0 16px 32px rgba(11, 31, 59, 0.08);
    --shadow-subtle: 0 8px 20px rgba(11, 31, 59, 0.06);
    --radius-lg: 16px;
    --radius-md: 12px;
    --radius-sm: 8px;
    --sidebar-compact: {sidebar_compact};
}}

html, body, [data-testid="stAppViewContainer"] {{
    background-color: var(--base-bg);
    color: var(--text-color);
    font-family: "Inter", "Source Sans 3", "Noto Sans JP", "Hiragino Sans", "Yu Gothic", sans-serif;
    font-size: calc(16px * var(--base-font-scale));
    line-height: 1.5;
    letter-spacing: 0.01em;
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum" 1, "liga" 1;
}}

h1, h2, h3, h4, h5, h6,
.stMarkdown h1,
.stMarkdown h2,
.stMarkdown h3,
.stMarkdown h4,
.stMarkdown h5,
.stMarkdown h6 {{
    font-family: "Inter", "Source Sans 3", "Noto Sans JP", "Hiragino Sans", sans-serif;
    font-weight: 700;
    letter-spacing: 0.01em;
    color: var(--primary);
}}

h1, .stMarkdown h1 {{ font-size: calc(1.75rem * var(--base-font-scale)); }}
h2, .stMarkdown h2 {{ font-size: calc(1.5rem * var(--base-font-scale)); }}
h3, .stMarkdown h3 {{ font-size: calc(1.25rem * var(--base-font-scale)); }}
h4, .stMarkdown h4 {{ font-size: calc(1.1rem * var(--base-font-scale)); }}
h5, .stMarkdown h5 {{ font-size: calc(1rem * var(--base-font-scale)); }}
h6, .stMarkdown h6 {{ font-size: calc(0.9rem * var(--base-font-scale)); }}

[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, rgba(11, 31, 59, 0.96) 0%, rgba(11, 31, 59, 0.92) 55%, rgba(30, 136, 229, 0.88) 100%);
    color: #F5F7FA;
    width: calc(18rem - 9rem * var(--sidebar-compact));
    min-width: calc(16rem - 8rem * var(--sidebar-compact));
    transition: width 0.35s ease;
    box-shadow: 16px 0 32px rgba(11, 31, 59, 0.2);
}}

[data-testid="stSidebar"] * {{
    color: #F5F7FA !important;
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] {{
    display: none !important;
}}

.sidebar-nav__header {{
    font-size: 0.95rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    opacity: 0.85;
    margin: 1rem 0 0.6rem 0;
}}

.sidebar-nav {{
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}}

[data-testid="stSidebar"] button[kind="secondary"] {{
    display: flex;
    align-items: center;
    justify-content: flex-start;
    gap: 0.6rem;
    padding: 0.75rem 0.9rem;
    border-radius: var(--radius-md);
    border: 1px solid rgba(255, 255, 255, 0.14);
    background: rgba(255, 255, 255, 0.08);
    color: #F5F7FA;
    font-weight: 600;
    transition: background 0.25s ease, transform 0.25s ease;
}}

[data-testid="stSidebar"] button[kind="secondary"]:hover:not(:disabled) {{
    background: rgba(255, 255, 255, 0.14);
    transform: translateX(2px);
}}

[data-testid="stSidebar"] button[kind="primary"] {{
    display: flex;
    align-items: center;
    justify-content: flex-start;
    gap: 0.7rem;
    padding: 0.85rem 1rem;
    border-radius: var(--radius-md);
    border: 1px solid rgba(255, 255, 255, 0.45);
    background: rgba(255, 255, 255, 0.24);
    color: #0B1F3B;
    font-weight: 700;
    box-shadow: 0 12px 28px rgba(255, 255, 255, 0.18);
}}

[data-testid="stSidebar"] button[kind="primary"]:disabled {{
    color: #0B1F3B;
}}

[data-testid="stSidebar"] button[kind="secondary"] span,
[data-testid="stSidebar"] button[kind="primary"] span {{
    font-size: 1rem;
    letter-spacing: 0.01em;
}}

.workflow-banner {{
    position: sticky;
    top: 0;
    z-index: 120;
    background: var(--surface);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-subtle);
    padding: 1.1rem 1.25rem;
    margin: -1rem -0.2rem 1.5rem -0.2rem;
    border: 1px solid var(--border-color);
}}

.workflow-banner__title {{
    font-weight: 700;
    letter-spacing: 0.02em;
    color: var(--primary);
    font-size: 1.05rem;
}}

.workflow-banner__list {{
    list-style: none;
    display: flex;
    gap: 0.9rem;
    margin: 0.85rem 0 0.5rem 0;
    padding: 0;
    overflow-x: auto;
}}

.workflow-banner__item {{
    display: flex;
    align-items: center;
    gap: 0.75rem;
    min-width: 210px;
    padding: 0.55rem 0.85rem;
    border-radius: var(--radius-md);
    border: 1px solid var(--border-color);
    background: var(--surface-alt);
    transition: border 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
}}

.workflow-banner__badge {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2.1rem;
    height: 2.1rem;
    border-radius: 999px;
    background: rgba(30, 136, 229, 0.14);
    color: var(--accent);
    font-weight: 700;
    font-size: 0.95rem;
}}

.workflow-banner__label {{
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
}}

.workflow-banner__label-text {{
    font-weight: 600;
    color: var(--primary);
}}

.workflow-banner__description {{
    font-size: 0.85rem;
    color: var(--text-subtle);
    line-height: 1.35;
}}

.workflow-banner__item--completed {{
    background: rgba(60, 122, 94, 0.12);
    border-color: rgba(60, 122, 94, 0.28);
}}

.workflow-banner__item--completed .workflow-banner__badge {{
    background: var(--positive);
    color: #ffffff;
}}

.workflow-banner__item--current {{
    background: rgba(30, 136, 229, 0.18);
    border-color: rgba(30, 136, 229, 0.45);
    box-shadow: 0 14px 32px rgba(30, 136, 229, 0.25);
}}

.workflow-banner__item--current .workflow-banner__badge {{
    background: var(--accent);
    color: #ffffff;
}}

.workflow-banner__item--upcoming {{
    opacity: 0.9;
}}

.workflow-banner__meta {{
    font-size: 0.85rem;
    color: var(--text-subtle);
}}

.sticky-tab-bar {{
    position: sticky;
    top: 136px;
    z-index: 90;
    background: var(--surface);
    padding: 0.7rem 1rem 0.5rem;
    margin: 0 -0.2rem 1.25rem -0.2rem;
    border-bottom: 1px solid var(--border-color);
    box-shadow: 0 18px 30px rgba(11, 31, 59, 0.08);
}}

.sticky-tab-bar [role="radiogroup"] {{
    justify-content: center;
    gap: 0.6rem;
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
    border-bottom: 1px solid rgba(11, 31, 59, 0.12);
    flex-wrap: wrap;
}}

.stTabs [role="tab"] {{
    font-weight: 600;
    padding: 0.75rem 1.2rem;
    border-radius: 14px 14px 0 0;
    background-color: transparent;
    color: var(--text-subtle);
    border: 1px solid transparent;
}}

.stTabs [role="tab"][aria-selected="true"] {{
    background-color: var(--surface);
    color: var(--primary);
    box-shadow: 0 -2px 20px rgba(11, 31, 59, 0.08);
    border-color: var(--border-color);
    border-bottom: 3px solid var(--accent);
}}

.hero-card {{
    position: relative;
    overflow: hidden;
    background: linear-gradient(135deg, rgba(11, 31, 59, 0.95) 0%, rgba(30, 136, 229, 0.9) 100%);
    color: #ffffff;
    padding: 32px;
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-soft);
    margin-bottom: 24px;
}}

.hero-card::before {{
    content: "";
    position: absolute;
    inset: -70px auto auto -90px;
    width: 240px;
    height: 240px;
    background: radial-gradient(circle at 60% 40%, rgba(255, 255, 255, 0.22), transparent 65%);
    opacity: 0.85;
}}

.hero-card::after {{
    content: "";
    position: absolute;
    right: -60px;
    top: -80px;
    width: 280px;
    height: 280px;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 280 280'%3E%3Cg fill='none' stroke='%23FFFFFF' stroke-width='6' stroke-linecap='round' stroke-opacity='0.35'%3E%3Ccircle cx='188' cy='86' r='46'/%3E%3Cpath d='M42 212c62-72 142-72 204-144'/%3E%3Cpath d='M64 252c84-52 158-116 216-188'/%3E%3C/g%3E%3C/svg%3E");
    background-size: contain;
    background-repeat: no-repeat;
    opacity: 0.55;
}}

.hero-card h1 {{
    margin: 0 0 12px 0;
    font-size: calc(1.75rem * var(--base-font-scale));
    font-weight: 700;
}}

.hero-card p {{
    margin: 0;
    font-size: calc(1.04rem * var(--base-font-scale));
    opacity: 0.92;
}}

.trust-badges {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    margin: -0.4rem 0 1.6rem 0;
}}

.trust-badge {{
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0.55rem 0.9rem;
    border-radius: 999px;
    background: rgba(30, 136, 229, 0.12);
    border: 1px solid rgba(11, 31, 59, 0.12);
    color: var(--accent);
    font-size: calc(0.9rem * var(--base-font-scale));
    font-weight: 500;
    box-shadow: 0 8px 20px rgba(11, 31, 59, 0.1);
}}

.trust-badge__icon {{
    font-size: 1.1rem;
}}

.trust-badge__text {{
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
}}

.section-heading {{
    display: flex;
    align-items: center;
    gap: 1rem;
    margin: 1.6rem 0 1rem;
}}

.section-heading__icon {{
    width: 48px;
    height: 48px;
    border-radius: var(--radius-md);
    position: relative;
    background: linear-gradient(135deg, rgba(30, 136, 229, 0.18) 0%, rgba(11, 31, 59, 0.12) 100%);
    border: 1px solid rgba(11, 31, 59, 0.2);
    box-shadow: var(--shadow-subtle);
}}

.section-heading__icon::after {{
    content: "";
    position: absolute;
    inset: 0;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 48 48'%3E%3Cg fill='none' stroke='%230B1F3B' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round' stroke-opacity='0.7'%3E%3Cpath d='M10 30c4-6 10-6 14-12s6-14 14-14'/%3E%3Cpath d='M8 14c6 0 12 6 12 12s6 10 12 10'/%3E%3C/g%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-size: 72%;
    background-position: center;
}}

.section-heading__title {{
    margin: 0;
    font-size: calc(1.45rem * var(--base-font-scale));
}}

.section-heading__subtitle {{
    margin: 0.2rem 0 0;
    font-size: calc(0.95rem * var(--base-font-scale));
    color: var(--text-subtle);
}}

.responsive-card-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(248px, 1fr));
    gap: 16px;
    width: 100%;
}}

.metric-card {{
    position: relative;
    overflow: hidden;
    background: var(--surface);
    border-radius: var(--radius-md);
    padding: 24px;
    box-shadow: var(--shadow-subtle);
    display: flex;
    flex-direction: column;
    gap: 12px;
    border: 1px solid var(--border-color);
}}

.metric-card::before {{
    content: "";
    position: absolute;
    left: -50px;
    bottom: -70px;
    width: 180px;
    height: 180px;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 180 180'%3E%3Cg fill='none' stroke='%230B1F3B' stroke-width='3' stroke-linecap='round' stroke-opacity='0.18'%3E%3Cpath d='M10 130c36-24 74-24 112-70'/%3E%3Cpath d='M22 158c44-26 98-66 148-122'/%3E%3C/g%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-size: cover;
}}

.metric-card::after {{
    content: "";
    position: absolute;
    top: -60px;
    right: -40px;
    width: 150px;
    height: 150px;
    background: radial-gradient(circle at center, rgba(30, 136, 229, 0.18), transparent 68%);
    opacity: 0.9;
}}

.metric-card--positive {{
    border-color: rgba(60, 122, 94, 0.45);
    box-shadow: 0 16px 28px rgba(60, 122, 94, 0.16);
}}

.metric-card--caution {{
    border-color: rgba(178, 123, 22, 0.4);
    box-shadow: 0 16px 28px rgba(178, 123, 22, 0.14);
}}

.metric-card--negative {{
    border-color: rgba(181, 80, 74, 0.4);
    box-shadow: 0 16px 28px rgba(181, 80, 74, 0.14);
}}

.metric-card__header {{
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: calc(0.95rem * var(--base-font-scale));
    color: var(--text-subtle);
}}

.metric-card__icon {{
    width: 32px;
    height: 32px;
    border-radius: var(--radius-sm);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: rgba(30, 136, 229, 0.12);
    color: var(--primary);
    font-size: 1rem;
    font-weight: 600;
}}

.metric-card__label {{
    font-weight: 600;
}}

.metric-card__trend {{
    margin-left: auto;
    font-size: calc(0.82rem * var(--base-font-scale));
    font-weight: 600;
    color: var(--accent);
}}

.metric-card__tone-badge {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    margin-left: 8px;
    padding: 2px 8px;
    border-radius: 999px;
    background: rgba(30, 136, 229, 0.12);
    font-size: calc(0.75rem * var(--base-font-scale));
    color: var(--primary);
}}
.metric-card__tone-text {{
    font-weight: 600;
    letter-spacing: 0.02em;
}}
.metric-card__value {{
    font-size: calc(1.45rem * var(--base-font-scale));
    font-weight: 700;
    color: var(--accent);
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
    position: relative;
    overflow: hidden;
    display: flex;
    gap: 12px;
    padding: 16px 20px;
    border-radius: var(--radius-md);
    margin-bottom: 16px;
    background: var(--surface);
    border-left: 6px solid var(--accent);
    box-shadow: var(--shadow-subtle);
    border: 1px solid var(--border-color);
}}

.callout::after {{
    content: "";
    position: absolute;
    right: -50px;
    top: -60px;
    width: 140px;
    height: 140px;
    background: radial-gradient(circle at center, rgba(30, 136, 229, 0.16), transparent 70%);
}}

.callout--positive {{
    border-left-color: var(--positive);
}}

.callout--caution {{
    border-left-color: var(--warning);
}}

.callout__icon {{
    width: 32px;
    height: 32px;
    border-radius: var(--radius-sm);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: rgba(30, 136, 229, 0.12);
    color: var(--primary);
    font-size: 1.1rem;
    font-weight: 600;
}}

.callout__title {{
    font-size: calc(1rem * var(--base-font-scale));
    color: var(--primary);
}}

.callout__body p {{
    margin: 0;
    font-size: calc(0.92rem * var(--base-font-scale));
}}

.form-card {{
    background: var(--surface);
    border-radius: var(--radius-lg);
    padding: 24px 28px;
    margin: 24px 0;
    box-shadow: var(--shadow-soft);
    border: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
    gap: 20px;
}}

.form-card__header {{
    display: flex;
    align-items: center;
    gap: 12px;
}}

.form-card__icon {{
    width: 36px;
    height: 36px;
    border-radius: var(--radius-sm);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: rgba(30, 136, 229, 0.14);
    color: var(--primary);
    font-size: 1.1rem;
    font-weight: 600;
}}

.form-card__heading {{
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
}}

.form-card__title {{
    margin: 0;
    font-size: calc(1.08rem * var(--base-font-scale));
    font-weight: 600;
}}

.form-card__subtitle {{
    margin: 0;
    font-size: calc(0.9rem * var(--base-font-scale));
    color: var(--text-subtle);
}}

.form-card__body {{
    display: flex;
    flex-direction: column;
    gap: 20px;
}}

.wizard-stepper {{
    margin: 24px 0;
    padding: 24px 28px;
    border-radius: var(--radius-lg);
    background: var(--surface);
    border: 1px solid var(--border-color);
    box-shadow: var(--shadow-soft);
}}

.wizard-stepper__progress {{
    position: relative;
    height: 8px;
    border-radius: 999px;
    background: rgba(11, 31, 59, 0.1);
    margin-bottom: 1.1rem;
    overflow: hidden;
}}

.wizard-stepper__progress-bar {{
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, rgba(30, 136, 229, 0.85) 0%, rgba(52, 124, 214, 0.85) 100%);
    border-radius: inherit;
    transition: width 0.4s ease;
}}

.wizard-stepper__list {{
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
}}

.wizard-stepper__item {{
    background: var(--surface-alt);
    border-radius: var(--radius-lg);
    padding: 12px 16px;
    display: flex;
    align-items: flex-start;
    gap: 10px;
    border: 1px solid var(--border-color);
    min-height: 72px;
}}

.wizard-stepper__item--completed {{
    background: rgba(60, 122, 94, 0.12);
    border-color: rgba(60, 122, 94, 0.3);
}}

.wizard-stepper__item--current {{
    background: rgba(30, 136, 229, 0.12);
    border-color: rgba(30, 136, 229, 0.3);
    box-shadow: 0 16px 28px rgba(30, 136, 229, 0.18);
}}

.wizard-stepper__bullet {{
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: rgba(30, 136, 229, 0.16);
    color: var(--primary);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
    font-size: 1rem;
}}

.wizard-stepper__text {{
    display: flex;
    flex-direction: column;
    gap: 4px;
}}

.wizard-stepper__step-index {{
    font-size: calc(0.82rem * var(--base-font-scale));
    color: var(--text-subtle);
    letter-spacing: 0.06em;
    text-transform: uppercase;
}}

.wizard-stepper__title {{
    font-size: calc(0.98rem * var(--base-font-scale));
    font-weight: 600;
    color: var(--primary);
}}

.wizard-stepper__description {{
    font-size: calc(0.82rem * var(--base-font-scale));
    color: var(--text-subtle);
}}

.wizard-stepper__meta {{
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    font-size: calc(0.85rem * var(--base-font-scale));
    color: var(--text-subtle);
    margin-bottom: 8px;
}}

.formula-highlight {{
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 16px 20px;
    border-radius: var(--radius-lg);
    background: var(--surface-alt);
    border: 1px solid var(--border-color);
    box-shadow: var(--shadow-subtle);
    margin: 16px 0;
}}

.formula-highlight__icon {{
    width: 40px;
    height: 40px;
    border-radius: 999px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: rgba(30, 136, 229, 0.16);
    color: var(--primary);
    font-size: 1.1rem;
    font-weight: 600;
}}

.formula-highlight__body strong {{
    display: block;
    margin-bottom: 4px;
    font-size: calc(1rem * var(--base-font-scale));
}}

.formula-highlight__body p {{
    margin: 0;
    font-size: calc(0.9rem * var(--base-font-scale));
    color: var(--text-subtle);
}}

.context-hint {{
    background: var(--surface);
    border-radius: var(--radius-lg);
    padding: 16px 20px;
    border: 1px solid var(--border-color);
    box-shadow: var(--shadow-subtle);
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 16px;
}}

.context-hint__title {{
    font-weight: 600;
    font-size: calc(0.95rem * var(--base-font-scale));
    color: var(--primary);
}}

.context-hint__summary {{
    margin: 0;
    font-size: calc(0.85rem * var(--base-font-scale));
    color: var(--text-subtle);
}}

.context-hint__metrics {{
    margin: 0;
    padding-left: 20px;
    display: grid;
    gap: 4px;
    font-size: calc(0.84rem * var(--base-font-scale));
    color: var(--text-subtle);
}}

.context-hint__footer {{
    margin-top: 0.15rem;
}}

.context-hint__link {{
    font-size: calc(0.84rem * var(--base-font-scale));
    color: var(--accent);
    text-decoration: underline;
}}

.security-panel {{
    margin-top: 24px;
    padding: 20px 24px;
    border-radius: var(--radius-lg);
    background: rgba(11, 31, 59, 0.06);
    border: 1px solid rgba(11, 31, 59, 0.15);
    box-shadow: var(--shadow-subtle);
}}

.security-panel__lead {{
    margin: 0 0 8px 0;
    font-weight: 600;
    color: var(--primary);
}}

.security-panel__badges {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-bottom: 0.6rem;
}}

.security-panel__list {{
    margin: 0;
    padding-left: 1.2rem;
    color: var(--text-subtle);
    font-size: calc(0.88rem * var(--base-font-scale));
    display: grid;
    gap: 0.35rem;
}}

.app-footer {{
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    padding: 0.6rem 0 1.2rem 0;
}}

.app-footer__trust {{
    display: flex;
    flex-direction: column;
    gap: 8px;
}}

.app-footer__security {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}}

.security-badge {{
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.35rem 0.7rem;
    border-radius: 999px;
    background: rgba(30, 136, 229, 0.14);
    color: var(--accent);
    font-size: calc(0.82rem * var(--base-font-scale));
    font-weight: 600;
    border: 1px solid rgba(11, 31, 59, 0.14);
}}

.app-footer__security-text {{
    margin: 0;
    font-size: calc(0.82rem * var(--base-font-scale));
    color: var(--text-subtle);
}}

.app-footer__expertise {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
}}

.expert-badge {{
    display: inline-flex;
    align-items: center;
    padding: 0.3rem 0.65rem;
    border-radius: 8px;
    background: rgba(11, 31, 59, 0.1);
    color: var(--primary);
    font-size: calc(0.8rem * var(--base-font-scale));
    font-weight: 600;
    letter-spacing: 0.02em;
}}

.app-footer__brand {{
    display: flex;
    align-items: center;
    gap: 0.65rem;
}}

.app-footer__logo {{
    width: 2.2rem;
    height: 2.2rem;
    border-radius: 16px;
    background: rgba(30, 136, 229, 0.14);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
    color: var(--primary);
}}

.app-footer__brand-name {{
    display: block;
    font-weight: 600;
}}

.app-footer__tagline {{
    display: block;
    font-size: calc(0.85rem * var(--base-font-scale));
    color: var(--text-subtle);
}}

.app-footer__links {{
    display: flex;
    gap: 0.5rem;
    align-items: center;
    font-size: calc(0.82rem * var(--base-font-scale));
}}

.app-footer__links a {{
    color: var(--accent);
    text-decoration: underline;
}}

.app-footer__caption {{
    margin: 0;
    font-size: calc(0.82rem * var(--base-font-scale));
    color: var(--text-subtle);
}}

.wizard-checklist {{
    display: grid;
    gap: 8px;
    padding: 8px 0;
}}

.wizard-checklist__item {{
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: calc(0.92rem * var(--base-font-scale));
}}

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
    position: relative;
    overflow: hidden;
    background: var(--surface);
    border-radius: var(--radius-md);
    padding: 20px;
    box-shadow: var(--shadow-subtle);
    border: 1px solid var(--border-color);
}}

[data-testid="stMetric"]::after {{
    content: "";
    position: absolute;
    top: -40px;
    right: -30px;
    width: 110px;
    height: 110px;
    background: radial-gradient(circle at center, rgba(30, 136, 229, 0.16), transparent 70%);
}}

[data-testid="stMetric"] [data-testid="stMetricLabel"] {{
    font-size: calc(0.92rem * var(--base-font-scale));
    color: var(--text-subtle);
}}

[data-testid="stMetric"] [data-testid="stMetricValue"] {{
    color: var(--accent);
    font-weight: 700;
    font-size: calc(1.3rem * var(--base-font-scale));
}}

[data-testid="stDataFrame"] {{
    background: var(--surface);
    border-radius: var(--radius-md);
    padding: 12px 16px 16px 16px;
    box-shadow: var(--shadow-subtle);
    border: 1px solid var(--border-color);
}}

button[kind="primary"] {{
    background: linear-gradient(135deg, rgba(30, 136, 229, 0.95) 0%, rgba(26, 96, 192, 0.95) 100%);
    border-radius: 999px;
    border: 1px solid rgba(11, 31, 59, 0.18);
    box-shadow: 0 18px 30px rgba(30, 136, 229, 0.25);
    color: #FFFFFF;
    letter-spacing: 0.02em;
    font-weight: 600;
}}

button[kind="primary"]:hover {{
    background: linear-gradient(135deg, rgba(66, 140, 229, 0.98) 0%, rgba(52, 124, 214, 0.98) 100%);
}}

button[kind="primary"]:focus-visible {{
    outline: 3px solid var(--accent) !important;
    outline-offset: 2px;
}}

.field-error {{
    border: 1px solid rgba(181, 80, 74, 0.5);
    border-radius: var(--radius-md);
    padding: 12px;
    background-color: rgba(181, 80, 74, 0.08);
    color: var(--negative);
}}

@media (max-width: 980px) {{
    .hero-card {{
        padding: 1.9rem 2rem;
    }}
    .responsive-card-grid {{
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    }}
    .form-card {{
        padding: 1.35rem 1.45rem;
    }}
    .wizard-stepper__list {{
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    }}
    [data-testid="stSidebar"] {{
        width: calc(17rem - 9rem * var(--sidebar-compact));
    }}
}}

@media (max-width: 640px) {{
    .section-heading {{
        align-items: flex-start;
    }}
    .section-heading__icon {{
        width: 2.6rem;
        height: 2.6rem;
    }}
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
        padding: 1.05rem 1.15rem;
    }}
    .responsive-card-grid {{
        grid-template-columns: 1fr;
    }}
    .form-card {{
        margin: 1rem 0;
        padding: 1.2rem 1.3rem;
    }}
    .wizard-stepper__list {{
        grid-template-columns: 1fr;
    }}
    .formula-highlight {{
        flex-direction: column;
        align-items: flex-start;
        gap: 0.75rem;
    }}
    .context-hint {{
        padding: 0.85rem 1rem;
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
