from pathlib import Path
import json
import urllib.request
import urllib.error

import streamlit as st
import streamlit.components.v1 as components

API_BASE = "https://multi-agent-api-2heu.onrender.com"

st.set_page_config(
    page_title="Multi-Agent Deliberation",
    page_icon="M",
    layout="wide",
    initial_sidebar_state="collapsed",
)

CURRENT_DIR = Path(__file__).resolve().parent
INDEX_HTML = CURRENT_DIR / "index.html"


def post_json(path, payload, timeout=600):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def stream_events(path, timeout=600):
    req = urllib.request.Request(API_BASE + path, method="GET")
    events = []

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()

            if not line.startswith("data: "):
                continue

            data = line[6:]

            if data == "[DONE]":
                break

            try:
                events.append(json.loads(data))
            except json.JSONDecodeError:
                pass

    return events


def run_deliberation(payload):
    topic = payload.get("topic", "")
    mode = payload.get("mode", "quick")
    quick_model = payload.get("quick_model", "deepseek-v4-pro")
    expert_models = payload.get("expert_models", {})
    api_keys = payload.get("api_keys", {})
    expert_api_keys = payload.get("expert_api_keys", {})

    start_result = post_json(
        "/api/deliberation/start",
        {
            "topic": topic,
            "question": "",
            "deliberation_mode": mode,
            "quick_model": quick_model,
            "expert_models": expert_models,
            "api_keys": api_keys,
            "expert_api_keys": expert_api_keys,
        },
    )

    events = stream_events("/api/deliberation/stream")

    return {
        "session_id": start_result.get("session_id", ""),
        "start": start_result,
        "events": events,
    }


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

if "deliberation_result" in st.session_state and st.session_state.deliberation_result is not None:
    result_json = json.dumps(
        st.session_state.deliberation_result,
        ensure_ascii=False,
    ).replace("</", "<\\/")

    html = f"<script>window.__DELIBERATION_RESULT__ = {result_json};</script>\n" + html
    st.session_state.deliberation_result = None

components.html(
    html,
    height=1100,
    scrolling=True,
)

payload_raw = st.query_params.get("_st_payload", "")

if payload_raw:
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        payload = {}

    st.query_params.clear()

    if payload.get("_st_action") == "run_deliberation":
        try:
            with st.spinner("多智能体议事进行中，请稍候..."):
                result = run_deliberation(payload)

            st.session_state.deliberation_result = result
            st.rerun()

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            st.error(f"API request failed: HTTP {e.code}")
            st.code(error_body)

        except Exception as e:
            st.error("API request failed")
            st.code(str(e))