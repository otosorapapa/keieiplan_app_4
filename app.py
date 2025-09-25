"""Streamlit entry point – forwards to the shared home page renderer."""
from __future__ import annotations

import streamlit as st

from views import render_home_page

st.set_page_config(
    page_title="経営ダッシュボード",
    page_icon=":bar_chart:",
    layout="wide",
)

render_home_page()
