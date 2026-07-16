"""
多智能体议事厅 · Streamlit 版
Multi-Agent Deliberation System — streamlit_app.py

 
部署到 Streamlit Community Cloud 时，Streamlit 会自动运行此文件。
"""

import streamlit as st
from pathlib import Path
import threading
import time
import sys

# ── 页面配置 ──────────────────────────────────────────────
st.set_page_config(
    page_title="多智能体议事厅",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── 在后台启动 FastAPI 后端 ────────────────────────────────────
@st.cache_resource
def _ensure_backend_running():
    """确保 FastAPI 后端在后台运行。cache_resource 保证只启动一次。"""
    import uvicorn
    sys.path.insert(0, str(Path(__file__).parent))

    def _run():
        from api.main import app as fastapi_app
        uvicorn.run(fastapi_app, host="127.0.0.1", port=8765, log_level="warning")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    time.sleep(2)
    return True

_backend_ready = _ensure_backend_running()

# ── 注册 API 代理 ─────────────────────────────────────────────
def _register_api_proxy():
    """在 Streamlit 的 Tornado 服务器上注册 /api/ 代理路由。"""
    try:
        from streamlit.web.server import Server
        import tornado.web
        import httpx

        server = Server.get_current()
        if server is None:
            return False

        tornado_app = server._tornado_web_app

        class APIProxy(tornado.web.RequestHandler):
            async def get(self):
                target = f"http://127.0.0.1:8765{self.request.uri}"
                headers = {k: v for k, v in self.request.headers.get_all()
                          if k.lower() not in ('host', 'content-length', 'connection')}
                async with httpx.AsyncClient(timeout=300.0) as client:
                    resp = await client.get(target, headers=headers)
                self.set_status(resp.status_code)
                for k, v in resp.headers.items():
                    if k.lower() not in ('content-length', 'transfer-encoding', 'connection'):
                        self.set_header(k, v)
                self.write(resp.content)

            async def post(self):
                target = f"http://127.0.0.1:8765{self.request.uri}"
                headers = {k: v for k, v in self.request.headers.get_all()
                          if k.lower() not in ('host', 'content-length', 'connection')}
                async with httpx.AsyncClient(timeout=300.0) as client:
                    resp = await client.post(target, content=self.request.body, headers=headers)
                self.set_status(resp.status_code)
                for k, v in resp.headers.items():
                    if k.lower() not in ('content-length', 'transfer-encoding', 'connection'):
                        self.set_header(k, v)
                self.write(resp.content)

        tornado_app.add_handlers(r".*", [(r"/api/.*", APIProxy)])
        return True
    except Exception:
        return False

_proxy_ready = _register_api_proxy()

# ── 加载并渲染前端 HTML ──────────────────────────────────
HTML_PATH = Path(__file__).parent / "frontend" / "index.html"

if not HTML_PATH.exists():
    st.error(f"Cannot find: {HTML_PATH}")
    st.stop()

html_content = HTML_PATH.read_text(encoding="utf-8")

# ── 注入 API 基础路径 ───────────────────────────────────────
_api_base_injection = """<script>
(function(){
  var host = window.location.hostname || '';
  var isCloud = host.indexOf('streamlit.app') !== -1;
  window.API_BASE = isCloud ? window.location.origin : 'http://localhost:8765';
})();
</script>"""

if "</head>" in html_content:
    html_content = html_content.replace("</head>", _api_base_injection + "\n</head>")
else:
    html_content = _api_base_injection + html_content

# 全屏渲染 HTML
st.components.v1.html(
    html_content,
    height=1080,
    scrolling=True,
)
