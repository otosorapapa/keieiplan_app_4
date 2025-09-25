"""Streamlit entry point – forwards to the shared home page renderer."""
from __future__ import annotations

import streamlit as st

from state import ensure_session_defaults
from theme import inject_theme
from ui.navigation import render_global_navigation, render_workflow_banner
from views import render_home_page

st.set_page_config(
    page_title="経営ダッシュボード",
    page_icon=":bar_chart:",
    layout="wide",
)

inject_theme()
ensure_session_defaults()
render_global_navigation("home")
render_workflow_banner("home")
render_home_page()
