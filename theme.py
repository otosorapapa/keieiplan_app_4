"""Centralised colour scheme, responsive layout tweaks and accessibility helpers."""
from __future__ import annotations

from typing import Dict

import streamlit as st

from services.security import enforce_https

THEME_COLORS: Dict[str, str] = {
    "background": "#F4F6FB",
    "surface": "#FFFFFF",
    "surface_alt": "#E7ECF7",
    "primary": "#1C6AD8",
    "primary_light": "#5A8FE4",
    "accent": "#0F2C4F",
    "positive": "#1F6B54",
    "positive_strong": "#0E3F2D",
    "negative": "#8A3542",
    "neutral": "#CBD4E4",
    "text": "#0B1D33",
    "text_subtle": "#4B5D75",
    "chart_blue": "#1C6AD8",
    "chart_orange": "#2E7ABF",
    "chart_green": "#4F8ED8",
    "chart_purple": "#7FA6E0",
}

DARK_THEME_COLORS: Dict[str, str] = {
    "background": "#061325",
    "surface": "#0F1F35",
    "surface_alt": "#172C4A",
    "primary": "#4A8DE8",
    "primary_light": "#74A5F1",
    "accent": "#0A1E3A",
    "positive": "#36B295",
    "positive_strong": "#1C7A60",
    "negative": "#D97582",
    "neutral": "#42577A",
    "text": "#E8EEF7",
    "text_subtle": "#B8C4D9",
    "chart_blue": "#4A8DE8",
    "chart_orange": "#6FA4E8",
    "chart_green": "#91B8F0",
    "chart_purple": "#BACFF7",
}

COLOR_BLIND_COLORS: Dict[str, str] = {
    "background": "#F4F7FB",
    "surface": "#FFFFFF",
    "surface_alt": "#E4EAF5",
    "primary": "#1E63B6",
    "primary_light": "#4D84CE",
    "accent": "#0E2950",
    "positive": "#226B93",
    "positive_strong": "#134361",
    "negative": "#8B4952",
    "neutral": "#C7D2E3",
    "text": "#0E223A",
    "text_subtle": "#45546B",
    "chart_blue": "#1E63B6",
    "chart_orange": "#3F7FB6",
    "chart_green": "#5F92C7",
    "chart_purple": "#7FA6D8",
}

HIGH_CONTRAST_COLORS: Dict[str, str] = {
    "background": "#040A16",
    "surface": "#0B1526",
    "surface_alt": "#122036",
    "primary": "#2F8BF5",
    "primary_light": "#63A5FF",
    "accent": "#FFFFFF",
    "positive": "#3CD3A7",
    "positive_strong": "#1E8A67",
    "negative": "#FF848E",
    "neutral": "#5F6E88",
    "text": "#FFFFFF",
    "text_subtle": "#D7E0F0",
    "chart_blue": "#63A5FF",
    "chart_orange": "#9FBFFB",
    "chart_green": "#C4DBFF",
    "chart_purple": "#E0EDFF",
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
    line-height: 1.62;
    letter-spacing: 0.01em;
}}

h1, h2, h3, h4, h5, h6,
.stMarkdown h1,
.stMarkdown h2,
.stMarkdown h3,
.stMarkdown h4,
.stMarkdown h5,
.stMarkdown h6 {{
    font-family: "Noto Serif JP", "Hiragino Mincho ProN", "Yu Mincho", "YuMincho", serif;
    font-weight: 600;
    letter-spacing: 0.02em;
    color: var(--text-color);
}}

[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, rgba(15, 44, 79, 0.92) 0%, rgba(28, 106, 216, 0.88) 100%);
    color: #F7FAFC;
    width: calc(18rem - 9rem * var(--sidebar-compact));
    min-width: calc(16rem - 8rem * var(--sidebar-compact));
    transition: width 0.35s ease;
    box-shadow: 12px 0 28px rgba(6, 19, 37, 0.2);
}}

[data-testid="stSidebar"] * {{
    color: #F7FAFC !important;
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] ul {{
    padding: 0.75rem 0.4rem 1.4rem 0.4rem;
    display: grid;
    gap: 0.35rem;
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a {{
    display: flex;
    align-items: center;
    gap: calc(0.8rem * (1 - var(--sidebar-compact)) + 0.4rem);
    padding: 0.6rem 1rem;
    border-radius: 14px;
    transition: background-color 0.25s ease, gap 0.2s ease, transform 0.25s ease;
    font-weight: 600;
    position: relative;
    backdrop-filter: blur(2px);
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover {{
    background-color: rgba(255, 255, 255, 0.16);
    transform: translateX(2px);
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a::before {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: calc(2.2rem - 0.8rem * var(--sidebar-compact));
    height: calc(2.2rem - 0.8rem * var(--sidebar-compact));
    border-radius: 16px;
    background: rgba(255, 255, 255, 0.14);
    border: 1px solid rgba(247, 250, 252, 0.25);
    margin-right: calc(0.45rem * (1 - var(--sidebar-compact)));
    font-size: 1.05rem;
    font-family: "Noto Sans JP", "Noto Sans Symbols", "Hiragino Sans", sans-serif;
    font-weight: 600;
    color: #F7FAFC;
    transition: background-color 0.25s ease, transform 0.25s ease;
    content: "";
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover::before {{
    background: rgba(255, 255, 255, 0.22);
    transform: translateY(-1px);
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] span {{
    opacity: calc(1 - 0.92 * var(--sidebar-compact));
    transition: opacity 0.25s ease;
    white-space: nowrap;
    pointer-events: none;
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Home"]::before {{
    content: "⌂";
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Inputs"]::before {{
    content: "✎";
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Analysis"]::before {{
    content: "▥";
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Scenarios"]::before {{
    content: "⧉";
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Report"]::before {{
    content: "⎘";
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Settings"]::before {{
    content: "⚙";
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] li:first-child a::before {{
    content: "⌂";
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] li:first-child a span,
[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Home"] span,
[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Inputs"] span,
[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Analysis"] span,
[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Scenarios"] span,
[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Report"] span,
[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Settings"] span {{
    font-size: 0;
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a span::after {{
    font-size: calc(1rem - 0.2rem * var(--sidebar-compact));
    color: #F7FAFC;
    letter-spacing: 0.02em;
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] li:first-child a span::after {{
    content: "ホーム";
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Home"] span::after {{
    content: "概要";
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Inputs"] span::after {{
    content: "入力";
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Analysis"] span::after {{
    content: "分析";
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Scenarios"] span::after {{
    content: "シナリオ";
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Report"] span::after {{
    content: "レポート";
}}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[href*="Settings"] span::after {{
    content: "設定";
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
    border-bottom: 1px solid rgba(15, 44, 79, 0.12);
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
    color: var(--accent);
    box-shadow: 0 -2px 24px rgba(15, 44, 79, 0.12);
    border-color: rgba(15, 44, 79, 0.18);
    border-bottom: 3px solid var(--primary);
}}

.hero-card {{
    position: relative;
    overflow: hidden;
    background: linear-gradient(135deg, rgba(10, 34, 68, 0.96) 0%, rgba(28, 106, 216, 0.92) 100%);
    color: #ffffff;
    padding: 2.4rem 3rem;
    border-radius: 28px;
    box-shadow: 0 28px 54px rgba(6, 19, 37, 0.32);
    margin-bottom: 1.75rem;
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
    margin: 0 0 0.6rem 0;
    font-size: calc(2.15rem * var(--base-font-scale));
    font-weight: 700;
}}

.hero-card p {{
    margin: 0;
    font-size: calc(1.04rem * var(--base-font-scale));
    opacity: 0.92;
}}

.section-heading {{
    display: flex;
    align-items: center;
    gap: 1rem;
    margin: 1.6rem 0 1rem;
}}

.section-heading__icon {{
    width: 3.1rem;
    height: 3.1rem;
    border-radius: 18px;
    position: relative;
    background: linear-gradient(135deg, rgba(28, 106, 216, 0.2) 0%, rgba(15, 44, 79, 0.16) 100%);
    border: 1px solid rgba(15, 44, 79, 0.22);
    box-shadow: 0 12px 24px rgba(6, 19, 37, 0.12);
}}

.section-heading__icon::after {{
    content: "";
    position: absolute;
    inset: 0;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 48 48'%3E%3Cg fill='none' stroke='%230F2C4F' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round' stroke-opacity='0.7'%3E%3Cpath d='M10 30c4-6 10-6 14-12s6-14 14-14'/%3E%3Cpath d='M8 14c6 0 12 6 12 12s6 10 12 10'/%3E%3C/g%3E%3C/svg%3E");
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
    font-family: "Noto Sans JP", "Hiragino Sans", "Yu Gothic", sans-serif;
}}

.responsive-card-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 1rem;
    width: 100%;
}}

.metric-card {{
    position: relative;
    overflow: hidden;
    background: linear-gradient(160deg, rgba(255, 255, 255, 0.94) 0%, rgba(231, 236, 247, 0.9) 100%);
    border-radius: 22px;
    padding: 1.3rem 1.55rem;
    box-shadow: 0 18px 32px rgba(6, 19, 37, 0.1);
    display: flex;
    flex-direction: column;
    gap: 0.55rem;
    border: 1px solid rgba(15, 44, 79, 0.08);
}}

.metric-card::before {{
    content: "";
    position: absolute;
    left: -50px;
    bottom: -70px;
    width: 180px;
    height: 180px;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 180 180'%3E%3Cg fill='none' stroke='%230F2C4F' stroke-width='3' stroke-linecap='round' stroke-opacity='0.18'%3E%3Cpath d='M10 130c36-24 74-24 112-70'/%3E%3Cpath d='M22 158c44-26 98-66 148-122'/%3E%3C/g%3E%3C/svg%3E");
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
    background: radial-gradient(circle at center, rgba(28, 106, 216, 0.18), transparent 68%);
    opacity: 0.9;
}}

.metric-card--positive {{
    border-color: rgba(31, 107, 84, 0.45);
    box-shadow: 0 18px 34px rgba(31, 107, 84, 0.16);
}}

.metric-card--caution {{
    border-color: rgba(15, 44, 79, 0.35);
    box-shadow: 0 18px 34px rgba(15, 44, 79, 0.12);
}}

.metric-card--negative {{
    border-color: rgba(138, 53, 66, 0.35);
    box-shadow: 0 18px 34px rgba(138, 53, 66, 0.12);
}}

.metric-card__header {{
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: calc(0.95rem * var(--base-font-scale));
    color: var(--text-subtle);
}}

.metric-card__icon {{
    width: 2.1rem;
    height: 2.1rem;
    border-radius: 14px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: rgba(28, 106, 216, 0.12);
    color: var(--accent);
    font-size: 1.05rem;
    font-weight: 600;
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
    background: rgba(15, 44, 79, 0.08);
    font-size: calc(0.75rem * var(--base-font-scale));
    color: var(--accent);
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
    position: relative;
    overflow: hidden;
    display: flex;
    gap: 0.9rem;
    padding: 1.15rem 1.3rem;
    border-radius: 18px;
    margin-bottom: 1.2rem;
    background: linear-gradient(120deg, rgba(255, 255, 255, 0.96) 0%, rgba(231, 236, 247, 0.92) 100%);
    border-left: 6px solid var(--primary);
    box-shadow: 0 18px 32px rgba(6, 19, 37, 0.12);
    border: 1px solid rgba(15, 44, 79, 0.08);
}}

.callout::after {{
    content: "";
    position: absolute;
    right: -50px;
    top: -60px;
    width: 140px;
    height: 140px;
    background: radial-gradient(circle at center, rgba(28, 106, 216, 0.16), transparent 70%);
}}

.callout--positive {{
    border-left-color: var(--positive);
}}

.callout--caution {{
    border-left-color: var(--accent);
}}

.callout__icon {{
    width: 2.2rem;
    height: 2.2rem;
    border-radius: 14px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: rgba(28, 106, 216, 0.12);
    color: var(--accent);
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
    background: linear-gradient(140deg, rgba(255, 255, 255, 0.98) 0%, rgba(231, 236, 247, 0.9) 100%);
    border-radius: 24px;
    padding: 1.6rem 1.8rem;
    margin: 1.2rem 0;
    box-shadow: 0 20px 36px rgba(6, 19, 37, 0.08);
    border: 1px solid rgba(15, 44, 79, 0.08);
    display: flex;
    flex-direction: column;
    gap: 1.2rem;
}}

.form-card__header {{
    display: flex;
    align-items: center;
    gap: 0.85rem;
}}

.form-card__icon {{
    width: 2.2rem;
    height: 2.2rem;
    border-radius: 16px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: rgba(28, 106, 216, 0.14);
    color: var(--accent);
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
    font-family: "Noto Sans JP", "Hiragino Sans", "Yu Gothic", sans-serif;
}}

.form-card__body {{
    display: flex;
    flex-direction: column;
    gap: 1.2rem;
}}

.wizard-stepper {{
    margin: 1rem 0 1.4rem;
    padding: 1.3rem 1.6rem;
    border-radius: 26px;
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(231, 236, 247, 0.92) 100%);
    border: 1px solid rgba(15, 44, 79, 0.1);
    box-shadow: 0 22px 40px rgba(6, 19, 37, 0.12);
}}

.wizard-stepper__progress {{
    position: relative;
    height: 8px;
    border-radius: 999px;
    background: rgba(15, 44, 79, 0.1);
    margin-bottom: 1.1rem;
    overflow: hidden;
}}

.wizard-stepper__progress-bar {{
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, rgba(28, 106, 216, 0.85) 0%, rgba(52, 124, 214, 0.85) 100%);
    border-radius: inherit;
    transition: width 0.4s ease;
}}

.wizard-stepper__list {{
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 0.75rem;
}}

.wizard-stepper__item {{
    background: rgba(15, 44, 79, 0.04);
    border-radius: 20px;
    padding: 0.75rem 1rem;
    display: flex;
    align-items: flex-start;
    gap: 0.65rem;
    border: 1px solid rgba(15, 44, 79, 0.08);
    min-height: 4.2rem;
}}

.wizard-stepper__item--completed {{
    background: rgba(28, 106, 216, 0.08);
    border-color: rgba(28, 106, 216, 0.18);
}}

.wizard-stepper__item--current {{
    background: linear-gradient(140deg, rgba(28, 106, 216, 0.2) 0%, rgba(15, 44, 79, 0.16) 100%);
    border-color: rgba(28, 106, 216, 0.3);
    box-shadow: 0 20px 36px rgba(28, 106, 216, 0.18);
}}

.wizard-stepper__bullet {{
    width: 2.2rem;
    height: 2.2rem;
    border-radius: 50%;
    background: rgba(28, 106, 216, 0.16);
    color: var(--accent);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
    font-size: 1.05rem;
}}

.wizard-stepper__text {{
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
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
    color: var(--accent);
}}

.wizard-stepper__description {{
    font-size: calc(0.82rem * var(--base-font-scale));
    color: var(--text-subtle);
}}

.wizard-stepper__meta {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    font-size: calc(0.85rem * var(--base-font-scale));
    color: var(--text-subtle);
    margin-bottom: 0.4rem;
}}

.formula-highlight {{
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem 1.2rem;
    border-radius: 20px;
    background: linear-gradient(120deg, rgba(28, 106, 216, 0.12) 0%, rgba(231, 236, 247, 0.8) 100%);
    border: 1px solid rgba(15, 44, 79, 0.12);
    box-shadow: 0 18px 34px rgba(6, 19, 37, 0.08);
    margin: 1.1rem 0;
}}

.formula-highlight__icon {{
    width: 2.4rem;
    height: 2.4rem;
    border-radius: 999px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: rgba(28, 106, 216, 0.16);
    color: var(--accent);
    font-size: 1.2rem;
    font-weight: 600;
}}

.formula-highlight__body strong {{
    display: block;
    margin-bottom: 0.2rem;
    font-size: calc(1.02rem * var(--base-font-scale));
}}

.formula-highlight__body p {{
    margin: 0;
    font-size: calc(0.9rem * var(--base-font-scale));
    color: var(--text-subtle);
}}

.context-hint {{
    background: rgba(255, 255, 255, 0.95);
    border-radius: 20px;
    padding: 1rem 1.2rem;
    border: 1px solid rgba(15, 44, 79, 0.1);
    box-shadow: 0 18px 30px rgba(6, 19, 37, 0.08);
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
    margin-bottom: 1rem;
}}

.context-hint__title {{
    font-weight: 600;
    font-size: calc(0.95rem * var(--base-font-scale));
    color: var(--accent);
}}

.context-hint__summary {{
    margin: 0;
    font-size: calc(0.85rem * var(--base-font-scale));
    color: var(--text-subtle);
}}

.context-hint__metrics {{
    margin: 0;
    padding-left: 1.1rem;
    display: grid;
    gap: 0.2rem;
    font-size: calc(0.82rem * var(--base-font-scale));
    color: var(--text-subtle);
}}

.context-hint__footer {{
    margin-top: 0.15rem;
}}

.context-hint__link {{
    font-size: calc(0.82rem * var(--base-font-scale));
    color: var(--primary);
    text-decoration: underline;
}}

.app-footer {{
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    padding: 0.6rem 0 1.2rem 0;
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
    background: rgba(28, 106, 216, 0.14);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
    color: var(--accent);
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
    color: var(--primary);
    text-decoration: underline;
}}

.app-footer__caption {{
    margin: 0;
    font-size: calc(0.82rem * var(--base-font-scale));
    color: var(--text-subtle);
}}

.wizard-checklist {{
    display: grid;
    gap: 0.35rem;
    padding: 0.4rem 0;
}}

.wizard-checklist__item {{
    display: flex;
    align-items: center;
    gap: 0.4rem;
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
    background: linear-gradient(155deg, rgba(255, 255, 255, 0.95) 0%, rgba(231, 236, 247, 0.9) 100%);
    border-radius: 18px;
    padding: 1rem 1.25rem;
    box-shadow: 0 16px 28px rgba(6, 19, 37, 0.1);
    border: 1px solid rgba(15, 44, 79, 0.08);
}}

[data-testid="stMetric"]::after {{
    content: "";
    position: absolute;
    top: -40px;
    right: -30px;
    width: 110px;
    height: 110px;
    background: radial-gradient(circle at center, rgba(28, 106, 216, 0.16), transparent 70%);
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
    background: linear-gradient(160deg, rgba(255, 255, 255, 0.98) 0%, rgba(231, 236, 247, 0.92) 100%);
    border-radius: 18px;
    padding: 0.7rem 0.9rem 1rem 0.9rem;
    box-shadow: 0 16px 28px rgba(6, 19, 37, 0.08);
    border: 1px solid rgba(15, 44, 79, 0.08);
}}

button[kind="primary"] {{
    background: linear-gradient(135deg, rgba(28, 106, 216, 0.95) 0%, rgba(26, 96, 192, 0.95) 100%);
    border-radius: 999px;
    border: 1px solid rgba(15, 44, 79, 0.18);
    box-shadow: 0 18px 30px rgba(28, 106, 216, 0.25);
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
    border: 1px solid rgba(138, 53, 66, 0.5);
    border-radius: 14px;
    padding: 0.85rem;
    background-color: rgba(138, 53, 66, 0.1);
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
