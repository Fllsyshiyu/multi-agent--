from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "frontend" / "live_deliberation.html"

st.set_page_config(
    page_title="多智能体议事厅",
    page_icon="🗣️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    #MainMenu, header, footer { visibility: hidden; }
    .block-container { padding: 0; max-width: 100%; }
    iframe { display: block; }
    </style>
    """,
    unsafe_allow_html=True,
)

if not HTML_PATH.exists():
    st.error(f"Missing frontend file: {HTML_PATH}")
    st.stop()

components.html(HTML_PATH.read_text(encoding="utf-8"), height=920, scrolling=False)
