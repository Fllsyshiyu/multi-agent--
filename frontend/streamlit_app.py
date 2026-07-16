from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Multi-Agent Deliberation",
    page_icon="🧠",
    layout="wide",
)

CURRENT_DIR = Path(__file__).resolve().parent
INDEX_HTML = CURRENT_DIR / "index.html"

st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container {
        padding: 0;
        max-width: 100%;
    }
    iframe {
        width: 100%;
        min-height: 100vh;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if not INDEX_HTML.exists():
    st.error(f"Cannot find: {INDEX_HTML}")
    st.stop()

html = INDEX_HTML.read_text(encoding="utf-8")

components.html(
    html,
    height=1100,
    scrolling=True,
)