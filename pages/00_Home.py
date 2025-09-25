"""Overview / tutorial page accessible from the sidebar."""
from __future__ import annotations

import streamlit as st

from state import ensure_session_defaults
from theme import inject_theme
from ui.navigation import render_global_navigation, render_workflow_banner
from views import render_home_page

st.set_page_config(
    page_title="経営計画スタジオ｜概要",
    page_icon="▥",
    layout="wide",
)

inject_theme()
ensure_session_defaults()
render_global_navigation("home")
render_workflow_banner("home")
render_home_page()
