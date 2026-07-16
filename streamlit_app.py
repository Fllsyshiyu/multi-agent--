"""
多智能体议事厅 · Streamlit 版
Multi-Agent Deliberation System — streamlit_app.py

部署到 Streamlit Community Cloud 时，Streamlit 会自动运行此文件。
"""

import streamlit as st
from pathlib import Path
import threading
import asyncio
import time
import os
import sys

# ── 页面配置 ──────────────────────────────────────────────
st.set_page_config(
    page_title="多智能体议事厅",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── 环境检测（多重判断）────────────────────────────────────────
# Check working directory: on cloud it's /mount/src/... or /app/...
# On local Windows it's C:\Users\...\Desktop\...
_root_lower = str(Path(__file__).resolve().parent).lower()
_CLOUD_DETECTED = not any([
    "desktop" in _root_lower,
    "\\users\\" in _root_lower,
]) or any([
    os.environ.get("STREAMLIT_SERVER_PORT"),
    os.path.exists("/.dockerenv"),
])
_CLOUD_URL = "https://multi-agent-yishi.streamlit.app"

# ── 启动 FastAPI 后端（线程 + asyncio）──────────────────────────
_API_HOST = "127.0.0.1"
_API_PORT = 8765

def _start_fastapi_backend():
    """在 daemon 线程中启动 uvicorn（asyncio + threading）。"""
    import uvicorn
    sys.path.insert(0, str(Path(__file__).parent))

    def _serve():
        from api.main import app as fastapi_app
        cfg = uvicorn.Config(fastapi_app, host=_API_HOST, port=_API_PORT, log_level="warning")
        srv = uvicorn.Server(cfg)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(srv.serve())

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    time.sleep(2)  # give uvicorn a moment to bind

try:
    _start_fastapi_backend()
except Exception:
    pass  # backend might already be running on reload

# ── 注册 API 代理到 Tornado（用 IOLoop callback 延迟注册）────────
def _register_api_proxy():
    def _patch():
        import requests as _req
        from streamlit.web.server import Server
        import tornado.web
        import json as _json
        server = Server.get_current()
        if server is None:
            return
        app = server._tornado_web_app

        class HealthHandler(tornado.web.RequestHandler):
            def get(self):
                self.set_header("Content-Type", "application/json")
                self.write(_json.dumps({"status":"ok","proxy":"active","note":"/api/* routes are proxied to backend"}))

        class APIProxy(tornado.web.RequestHandler):
            def _do_proxy(self):
                target = f"http://{_API_HOST}:{_API_PORT}{self.request.uri}"
                hdrs = {k: v for k, v in self.request.headers.get_all()
                       if k.lower() not in ("host","content-length","connection")}
                try:
                    resp = _req.request(
                        self.request.method, target,
                        headers=hdrs, data=self.request.body or None,
                        timeout=300,
                    )
                    self.set_status(resp.status_code)
                    for k, v in resp.headers.items():
                        if k.lower() not in ("content-length","transfer-encoding","connection"):
                            self.set_header(k, v)
                    self.write(resp.content)
                except Exception:
                    self.set_status(502)
                    self.write(b'{"error":"backend unreachable"}')

            get = post = put = delete = patch = options = _do_proxy

        app.add_handlers(r".*", [(r"/api/health", HealthHandler)])
        app.add_handlers(r".*", [(r"/api/.*", APIProxy)])
        print("[proxy] registered", flush=True)

    try:
        import tornado.ioloop
        tornado.ioloop.IOLoop.current().add_callback(_patch)
    except Exception:
        pass

_register_api_proxy()

# ── 加载并渲染前端 HTML ──────────────────────────────────
HTML_PATH = Path(__file__).parent / "frontend" / "index.html"

if not HTML_PATH.exists():
    st.error(f"Cannot find: {HTML_PATH}")
    st.stop()

html_content = HTML_PATH.read_text(encoding="utf-8")

# ── 注入诊断 + API 基础路径 ──────────────────────────────────
if _CLOUD_DETECTED:
    _injection = '<base href="https://multi-agent-yishi.streamlit.app/">\n<script>window.API_BASE="";window.__CLOUD=1;</script>'
else:
    _injection = '<script>window.API_BASE="http://localhost:8765";window.__CLOUD=0;</script>'

# Inject at the VERY BEGINNING of HTML (before any tag)
html_content = _injection + "\n" + html_content

# 全屏渲染 HTML
st.components.v1.html(
    html_content,
    height=1080,
    scrolling=True,
)
