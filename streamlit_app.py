"""
多智能体议事厅 · Streamlit 版 v12
启动 FastAPI 后端 + Tornado 代理，所有 /api/* 请求由同容器内的 FastAPI 处理。
"""

import streamlit as st
from pathlib import Path
from datetime import datetime
import json, gc, sys, threading, time
import urllib.request, urllib.error

sys.path.insert(0, str(Path(__file__).parent / "src"))

# ── 步骤1: 启动 FastAPI 后端 ──
_fastapi_ready = False

def _start_fastapi():
    global _fastapi_ready
    import uvicorn
    from api.main import app
    # 先标记就绪再启动（uvicorn.run 是阻塞的）
    _fastapi_ready = True
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")

threading.Thread(target=_start_fastapi, daemon=True).start()

# 等待 FastAPI 就绪（最多等5秒）
for _ in range(50):
    if _fastapi_ready:
        time.sleep(0.3)  # 给 uvicorn 一点时间绑定端口
        break
    time.sleep(0.1)

# ── 步骤2: 注册 Tornado 代理处理器 ──
# 捕获所有 /api/* 请求并转发给 FastAPI (127.0.0.1:8765)

def _register_proxy():
    """在 Tornado 上注册 /api/* 代理路由。"""
    import tornado.web

    class APIProxy(tornado.web.RequestHandler):
        def prepare(self):
            target = f"http://127.0.0.1:8765{self.request.uri}"
            headers = {}
            for k in self.request.headers:
                if k.lower() not in ('host', 'connection', 'content-length'):
                    headers[k] = self.request.headers[k]
            data = self.request.body or None
            req = urllib.request.Request(target, data=data, headers=headers, method=self.request.method)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    self.set_status(resp.status)
                    for key, val in resp.headers.items():
                        if key.lower() not in ('transfer-encoding', 'content-encoding'):
                            self.set_header(key, val)
                    self.write(resp.read())
            except urllib.error.HTTPError as e:
                self.set_status(e.code)
                body = e.read()
                self.write(body)
            except Exception as e:
                self.set_status(502)
                self.write(json.dumps({"error": f"API proxy: {e}"}))

    # 三种方法找 Tornado app
    app = None
    try:
        from streamlit.web.server import Server
        server = Server.get_current()
        if server: app = server._tornado_web_app
        if app: print("[PROXY] Found Tornado via Server", flush=True)
    except: pass

    if app is None:
        for obj in gc.get_objects():
            if isinstance(obj, tornado.web.Application):
                app = obj
                print("[PROXY] Found Tornado via gc", flush=True)
                break

    if app is None:
        try:
            from streamlit.runtime import Runtime
            rt = Runtime.instance()
            for attr in ['_server', 'server']:
                srv = getattr(rt, attr, None)
                if srv and hasattr(srv, '_tornado_web_app'):
                    app = srv._tornado_web_app
                    print(f"[PROXY] Found Tornado via Runtime.{attr}", flush=True)
                    break
        except: pass

    if app:
        app.add_handlers(r".*", [(r"/api/.*", APIProxy)])
        print("[PROXY] /api/* → 127.0.0.1:8765 registered", flush=True)
        return True
    else:
        print("[PROXY] FAILED: Cannot find Tornado", flush=True)
        return False

proxy_ok = _register_proxy()

# ── 步骤3: Streamlit 页面 ──
st.set_page_config(page_title="多智能体议事厅", page_icon="🏛️", layout="wide", initial_sidebar_state="collapsed")

status_color = "#10b981" if proxy_ok else "#f59e0b"
status_text = f"API proxy {'OK' if proxy_ok else 'FAILED'}"
st.markdown(
    f'<div style="text-align:center;padding:5px;background:{status_color};color:#000;font-size:12px;font-weight:700">'
    f'✅ v12 · {datetime.now():%Y-%m-%d %H:%M} · {status_text}'
    '</div>',
    unsafe_allow_html=True,
)

# ── 步骤4: 加载并修复 HTML ──
HTML_PATH = Path(__file__).parent / "frontend" / "index.html"
if not HTML_PATH.exists():
    st.error(f"Cannot find: {HTML_PATH}")
    st.stop()

html_content = HTML_PATH.read_text(encoding="utf-8")

# CSS 修复
html_content = html_content.replace(
    '.topic-input-row{display:flex;align-items:center;gap:6px;margin-bottom:8px}',
    '.topic-input-row{display:flex;align-items:center;gap:6px;margin-bottom:8px;flex-wrap:nowrap}')
html_content = html_content.replace(
    '.assign-status.error{color:var(--err)}',
    '.assign-status.error{color:var(--err)}.assign-status.done{color:#6ee7b7;font-size:9px}')

# JS: fetch 拦截器 — API 返回 HTML 时抛错触发降级
html_content = html_content.replace('</head>',
    '<script>(function(){var _f=window.fetch;window.fetch=function(u,o){return _f(u,o).then(function(r){if(typeof u==="string"&&u.indexOf("/api/")>=0){var ct=r.headers.get("content-type")||"";if(!ct.includes("application/json")){var e=new Error("API HTML");e.isApiHtml=!0;throw e}}return r})}})()</script></head>')

st.components.v1.html(html_content, height=2000, scrolling=True)
