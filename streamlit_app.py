"""
多智能体议事厅 · Streamlit 版
部署到 Streamlit Community Cloud 时自动运行。
内嵌 Tornado API 处理器，前端 fetch 请求直接由本进程响应。
"""

import streamlit as st
from pathlib import Path
from datetime import datetime
import json
import gc
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))

# ── 内嵌 API 后端 ──
# 在 Streamlit 的 Tornado 服务器上注册 /api/* 路由，
# 前端 iframe 里的 fetch("/api/topic/assign_agents") 可以同源请求。
if "api_registered" not in st.session_state:
    try:
        import tornado.web
        from ma_deliberation_demo.role_assigner import assign_agents_for_topic, FACILITATOR_AGENTS

        class AssignAgentsHandler(tornado.web.RequestHandler):
            def set_default_headers(self):
                self.set_header("Access-Control-Allow-Origin", "*")
                self.set_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
                self.set_header("Access-Control-Allow-Headers", "Content-Type")

            def options(self):
                self.set_status(204)
                self.finish()

            def post(self):
                try:
                    body = json.loads(self.request.body)
                    topic = body.get("topic", "")
                    result = assign_agents_for_topic(topic)
                    self.set_header("Content-Type", "application/json")
                    self.write(json.dumps({
                        "success": True,
                        "analysis": result["analysis"],
                        "agents": result["agents"],
                        "facilitators": FACILITATOR_AGENTS,
                    }, ensure_ascii=False))
                except Exception as e:
                    self.set_status(500)
                    self.write(json.dumps({"success": False, "error": str(e)}))

        # Find Tornado app and register route
        found = False
        for obj in gc.get_objects():
            if isinstance(obj, tornado.web.Application):
                try:
                    obj.add_handlers(r".*", [(r"/api/topic/assign_agents", AssignAgentsHandler)])
                    found = True
                except Exception:
                    pass
        if found:
            print("[API] Tornado handler registered: /api/topic/assign_agents", flush=True)
    except Exception as e:
        print(f"[API] Registration failed (non-fatal): {e}", flush=True)
    st.session_state.api_registered = True

# ── 页面配置 ──
st.set_page_config(
    page_title="多智能体议事厅",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    '<div style="text-align:center;padding:5px;background:#10b981;color:#000;font-size:12px;font-weight:700">'
    '✅ v5 · ' + datetime.now().strftime('%Y-%m-%d %H:%M') + ' · API内嵌 · 角色分配可用'
    '</div>',
    unsafe_allow_html=True,
)

# ── 加载并渲染前端 HTML ──
HTML_PATH = Path(__file__).parent / "frontend" / "index.html"
if not HTML_PATH.exists():
    st.error(f"Cannot find: {HTML_PATH}")
    st.stop()

html_content = HTML_PATH.read_text(encoding="utf-8")
st.components.v1.html(html_content, height=2000, scrolling=True)
