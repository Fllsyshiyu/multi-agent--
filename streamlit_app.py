"""
多智能体议事厅 · Streamlit 版
Multi-Agent Deliberation System — streamlit_app.py
部署到 Streamlit Community Cloud 时，Streamlit 会自动运行此文件。
"""

import streamlit as st
from pathlib import Path
import sys
import json
import concurrent.futures

# ── 页面配置 ──────────────────────────────────────────────
st.set_page_config(
    page_title="多智能体议事厅",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── 确保 src 可导入 ─────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

# ── 在进程内调用 FastAPI（不启动服务器、不走网络）─────────────
def _run_deliberation_in_process(topic, mode, quick_model, expert_models, api_keys, expert_api_keys):
    """Use httpx.ASGITransport to call the FastAPI app in-process.
    Returns (session_id, list_of_events)."""
    import asyncio as _asyncio
    import httpx
    from api.main import app as fastapi_app

    async def _run():
        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://_", timeout=600) as client:
            resp = await client.post("/api/deliberation/start", json={
                "topic": topic, "question": "",
                "deliberation_mode": mode,
                "quick_model": quick_model,
                "expert_models": expert_models,
                "api_keys": api_keys,
                "expert_api_keys": expert_api_keys,
            })
            resp.raise_for_status()
            session_id = resp.json().get("session_id", "")

            events = []
            async with client.stream("GET", "/api/deliberation/stream") as stream:
                async for line in stream.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            events.append(json.loads(data))
                        except json.JSONDecodeError:
                            pass
            return {"session_id": session_id, "events": events}

    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(_asyncio.run, _run()).result(timeout=600)

# ── 加载并渲染前端 HTML ──────────────────────────────────
HTML_PATH = Path(__file__).parent / "frontend" / "index.html"

if not HTML_PATH.exists():
    st.error(f"Cannot find: {HTML_PATH}")
    st.stop()

html_content = HTML_PATH.read_text(encoding="utf-8")

# ── 注入预计算的结果（如果有）──────────────────────────────────
if "deliberation_result" in st.session_state and st.session_state.deliberation_result is not None:
    result = st.session_state.deliberation_result
    result_json = json.dumps(result)
    injection = f"<script>window.__DELIBERATION_RESULT__={result_json};</script>"
    html_content = injection + "\n" + html_content
    st.session_state.deliberation_result = None

# ── 渲染组件 ──────────────────────────────────────────────
component_result = st.components.v1.html(
    html_content,
    height=1080,
    scrolling=True,
)

# ── 处理前端发来的议事请求 ──────────────────────────────────
if component_result and isinstance(component_result, dict):
    if component_result.get("_st_action") == "run_deliberation":
        with st.spinner("🤖 多智能体议事进行中，请稍候..."):
            result = _run_deliberation_in_process(
                component_result.get("topic", ""),
                component_result.get("mode", "quick"),
                component_result.get("quick_model", "deepseek-v4-pro"),
                component_result.get("expert_models", {}),
                component_result.get("api_keys", {}),
                component_result.get("expert_api_keys", {}),
            )
        st.session_state.deliberation_result = result
        st.rerun()
