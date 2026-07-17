"""
多智能体议事厅 · Streamlit 版
Multi-Agent Deliberation System — streamlit_app.py


部署到 Streamlit Community Cloud 时，Streamlit 会自动运行此文件。
"""

import streamlit as st
from pathlib import Path
import subprocess
import sys
import os
import atexit

# ── 页面配置 ──────────────────────────────────────────────
st.set_page_config(
    page_title="多智能体议事厅",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── 环境检测 ──────────────────────────────────────────────────
_is_streamlit_cloud = bool(
    os.environ.get("STREAMLIT_RUNTIME_VERSION")
    or os.environ.get("STREAMLIT_CLOUD", "")
)

# ── 启动 FastAPI 后端（子进程）─────────────────────────────────
_API_PORT = 8765
_backend_proc = None

def _start_fastapi_backend():
    """用 subprocess 启动 FastAPI，比 threading 更可靠。"""
    global _backend_proc
    api_main = Path(__file__).parent / "api" / "main.py"
    _backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app",
         "--host", "127.0.0.1", "--port", str(_API_PORT), "--log-level", "warning"],
        cwd=str(Path(__file__).parent),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    atexit.register(lambda: _backend_proc and _backend_proc.terminate())

_start_fastapi_backend()

# ── 注册 API 代理到 Tornado ──────────────────────────────────
def _register_api_proxy():
    """通过 Tornado IOLoop 注册 /api/ 代理路由，延迟到 server 就绪后执行。"""
    def _patch():
        import requests as _req
        from streamlit.web.server import Server
        import tornado.web
        server = Server.get_current()
        if server is None:
            return
        app = server._tornado_web_app

        class APIProxy(tornado.web.RequestHandler):
            def _do_proxy(self):
                target = f"http://127.0.0.1:{_API_PORT}{self.request.uri}"
                headers = {}
                for k in self.request.headers:
                    kl = k.lower()
                    if kl not in ("host", "content-length", "connection"):
                        headers[k] = self.request.headers[k]
                method = self.request.method
                body = self.request.body if method in ("POST", "PUT", "PATCH") else None
                try:
                    resp = _req.request(method, target, headers=headers,
                                       data=body, stream=True, timeout=300)
                    self.set_status(resp.status_code)
                    for k, v in resp.headers.items():
                        kl = k.lower()
                        if kl not in ("content-length", "transfer-encoding", "connection"):
                            self.set_header(k, v)
                    self.write(resp.content)
                except Exception:
                    self.set_status(502)
                    self.write(b'{"error":"backend unreachable"}')

            get = _do_proxy
            post = _do_proxy
            put = _do_proxy
            delete = _do_proxy
            patch = _do_proxy
            options = _do_proxy

        # Only add if not already registered
        app.add_handlers(r".*", [(r"/api/.*", APIProxy)])
        print("[proxy] API routes registered", flush=True)

    import tornado.ioloop
    tornado.ioloop.IOLoop.current().add_callback(_patch)

_register_api_proxy()

# ── 加载并渲染前端 HTML ──────────────────────────────────
HTML_PATH = Path(__file__).parent / "frontend" / "index.html"

if not HTML_PATH.exists():
    st.error(f"Cannot find: {HTML_PATH}")
    st.stop()

html_content = HTML_PATH.read_text(encoding="utf-8")

# ── 注入 API 基础路径（Python 端直接决定，不依赖浏览器检测）─────
_api_base_injection = """<script>
(function(){
  // st.components.v1.html renders in a sandboxed about:blank iframe.
  // window.location.origin is null, window.parent is blocked.
  // Use document.referrer to get the parent page URL.
  var origin = '';
  try {
    var ref = document.referrer;
    if (ref) {
      var m = ref.match(/^(https?:\\/\\/[^\\/]+)/);
      if (m) origin = m[1];
    }
  } catch(e) {}
  var isCloud = origin.indexOf('streamlit.app') !== -1;
  window.API_BASE = isCloud ? origin : 'http://localhost:8765';
  console.log('[init] referrer origin =', JSON.stringify(origin), '| API_BASE =', JSON.stringify(window.API_BASE));
})();
</script>"""

if "</head>" in html_content:
    html_content = html_content.replace("</head>", _api_base_injection + "\n</head>", 1)
else:
    html_content = _api_base_injection + html_content

# 全屏渲染 HTML
st.components.v1.html(
    html_content,
    height=1080,
    scrolling=True,
)
