"""
多智能体议事厅 · Streamlit 版
Multi-Agent Deliberation System — streamlit_app.py

部署到 Streamlit Community Cloud 时，Streamlit 会自动运行此文件。
"""

import streamlit as st
from pathlib import Path

# ── 页面配置 ──────────────────────────────────────────────
st.set_page_config(
    page_title="多智能体议事厅",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── 加载并渲染前端 HTML ──────────────────────────────────
HTML_PATH = Path(__file__).parent / "frontend" / "index.html"

if not HTML_PATH.exists():
    st.error(f"Cannot find: {HTML_PATH}")
    st.stop()

html_content = HTML_PATH.read_text(encoding="utf-8")

# 全屏渲染 HTML
st.components.v1.html(
    html_content,
    height=1080,
    scrolling=True,
)
