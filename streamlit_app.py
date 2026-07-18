"""
多智能体议事厅 · Streamlit 版 v11
每次脚本运行都尝试在 Tornado 上注册 /api/* 路由（不用缓存）。
"""

import streamlit as st
from pathlib import Path
from datetime import datetime
import json
import gc
import sys
import traceback

sys.path.insert(0, str(Path(__file__).parent / "src"))

# ── 注册 Tornado API 处理器 ──
# 不用 @st.cache_resource（避免缓存失败结果）
# 每次脚本运行都尝试注册（幂等操作，重复注册无害）

def _find_tornado_app():
    """用三种方法查找 Streamlit 的 Tornado Application。"""
    import tornado.web

    # 方法 1: Server.get_current()
    try:
        from streamlit.web.server import Server
        server = Server.get_current()
        if server is not None:
            app = server._tornado_web_app
            print("[API] Found Tornado via Server.get_current()", flush=True)
            return app
    except Exception as e:
        print(f"[API] Server.get_current() failed: {e}", flush=True)

    # 方法 2: gc.get_objects()
    for obj in gc.get_objects():
        if isinstance(obj, tornado.web.Application):
            print("[API] Found Tornado via gc.get_objects()", flush=True)
            return obj

    # 方法 3: Runtime.instance()
    try:
        from streamlit.runtime import Runtime
        rt = Runtime.instance()
        for attr in ['_server', 'server']:
            srv = getattr(rt, attr, None)
            if srv:
                app = getattr(srv, '_tornado_web_app', None) or getattr(srv, '_app', None)
                if app:
                    print(f"[API] Found Tornado via Runtime.{attr}", flush=True)
                    return app
    except Exception as e:
        print(f"[API] Runtime fallback failed: {e}", flush=True)

    return None


def register_handlers():
    """注册 API 路由。返回 (success, message)。"""
    try:
        import tornado.web
        from ma_deliberation_demo.role_assigner import assign_agents_for_topic, FACILITATOR_AGENTS

        app = _find_tornado_app()
        if app is None:
            return False, "Cannot find Tornado Application"

        # 检查是否已注册（避免重复）
        existing = [r for r, h in app.default_router.rules if '/api/topic/assign_agents' in str(r)]
        if existing:
            print("[API] Route already registered, skipping", flush=True)
            return True, "Already registered"

        class Handler(tornado.web.RequestHandler):
            def set_default_headers(self):
                self.set_header("Access-Control-Allow-Origin", "*")
                self.set_header("Access-Control-Allow-Methods", "POST,OPTIONS")
                self.set_header("Access-Control-Allow-Headers", "Content-Type")
            def options(self):
                self.set_status(204); self.finish()
            def post(self):
                try:
                    body = json.loads(self.request.body)
                    r = assign_agents_for_topic(body.get("topic", ""))
                    self.set_header("Content-Type", "application/json")
                    self.write(json.dumps({"success":True,"analysis":r["analysis"],"agents":r["agents"],"facilitators":FACILITATOR_AGENTS}, ensure_ascii=False))
                except Exception as ex:
                    self.set_status(500)
                    self.write(json.dumps({"success":False,"error":str(ex)}))

        app.add_handlers(r".*", [(r"/api/topic/assign_agents", Handler)])
        print("[API] Route registered: POST /api/topic/assign_agents", flush=True)
        return True, "Route registered"

    except Exception as e:
        print(f"[API] Handler registration failed: {e}", flush=True)
        traceback.print_exc()
        return False, str(e)

# 每次运行时注册
api_ok, api_msg = register_handlers()

# ── 页面 ──
st.set_page_config(page_title="多智能体议事厅", page_icon="🏛️", layout="wide", initial_sidebar_state="collapsed")

if api_ok:
    st.markdown(f'<div style="text-align:center;padding:5px;background:#10b981;color:#000;font-size:12px;font-weight:700">✅ v11 · {datetime.now():%Y-%m-%d %H:%M} · API已注册</div>', unsafe_allow_html=True)
else:
    st.markdown(f'<div style="text-align:center;padding:5px;background:#f59e0b;color:#000;font-size:12px;font-weight:700">⚠️ v11 · {datetime.now():%Y-%m-%d %H:%M} · {api_msg}</div>', unsafe_allow_html=True)

# ── 加载 HTML ──
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

# fetch 拦截器 — API 返回 HTML 时自动抛错触发降级
html_content = html_content.replace('</head>',
    '<script>(function(){var _f=window.fetch;window.fetch=function(u,o){return _f(u,o).then(function(r){if(typeof u==="string"&&u.indexOf("/api/")>=0){var ct=r.headers.get("content-type")||"";if(!ct.includes("application/json")){var e=new Error("API HTML");e.isApiHtml=!0;throw e}}return r})}})()</script></head>')

st.components.v1.html(html_content, height=2000, scrolling=True)
