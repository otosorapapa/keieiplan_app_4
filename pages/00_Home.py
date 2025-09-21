"""Overview / tutorial page accessible from the sidebar."""
from __future__ import annotations

import streamlit as st

from views import render_home_page

st.set_page_config(
    page_title="経営計画スタジオ｜概要",
    page_icon="📊",
    layout="wide",
)

render_home_page()
