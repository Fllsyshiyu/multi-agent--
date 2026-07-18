"""
多智能体议事厅 · Streamlit 版
部署到 Streamlit Community Cloud 时自动运行。
前端 HTML 内置本地 agent 生成引擎，无需额外 API 后端即可完成角色分配。
"""

import streamlit as st
from pathlib import Path
from datetime import datetime

# ── 页面配置 ──
st.set_page_config(
    page_title="多智能体议事厅",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    '<div style="text-align:center;padding:5px;background:#10b981;color:#000;font-size:12px;font-weight:700">'
    '✅ v7 · ' + datetime.now().strftime('%Y-%m-%d %H:%M') + ' · 本地引擎 · 角色分配可用'
    '</div>',
    unsafe_allow_html=True,
)

HTML_PATH = Path(__file__).parent / "frontend" / "index.html"
if not HTML_PATH.exists():
    st.error(f"Cannot find: {HTML_PATH}")
    st.stop()

html_content = HTML_PATH.read_text(encoding="utf-8")
st.components.v1.html(html_content, height=2000, scrolling=True)
