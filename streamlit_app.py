"""
多智能体议事厅 · Streamlit 版 v10
通过 Tornado 路由注册在 Streamlit 进程内提供 /api/* 端点。
前端 fetch 请求同源响应，无需额外后端服务。
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
# 关键：必须在 Streamlit Server 启动后注册。用 st.cache_resource 确保持久化。
@st.cache_resource
def register_api_handlers():
    """在 Streamlit 的 Tornado 服务器上注册 /api/* 路由。返回是否成功。"""
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

        # 方法 1: Server.get_current()
        tornado_app = None
        try:
            from streamlit.web.server import Server
            server = Server.get_current()
            if server is not None:
                tornado_app = server._tornado_web_app
                print("[API] Found Tornado via Server.get_current()", flush=True)
        except Exception:
            pass

        # 方法 2: gc.get_objects()
        if tornado_app is None:
            for obj in gc.get_objects():
                if isinstance(obj, tornado.web.Application):
                    tornado_app = obj
                    print("[API] Found Tornado via gc.get_objects()", flush=True)
                    break

        # 方法 3: Runtime
        if tornado_app is None:
            try:
                from streamlit.runtime import Runtime
                rt = Runtime.instance()
                for attr in ['_server', 'server']:
                    srv = getattr(rt, attr, None)
                    if srv:
                        tornado_app = getattr(srv, '_tornado_web_app', None)
                        if tornado_app: break
                if tornado_app:
                    print("[API] Found Tornado via Runtime", flush=True)
            except Exception:
                pass

        if tornado_app is None:
            print("[API] FAILED: Cannot find Tornado Application", flush=True)
            return False

        # 注册路由
        tornado_app.add_handlers(r".*", [(r"/api/topic/assign_agents", AssignAgentsHandler)])
        print("[API] Route registered: POST /api/topic/assign_agents", flush=True)
        return True

    except Exception as e:
        print(f"[API] Exception: {e}", flush=True)
        traceback.print_exc()
        return False

api_ok = register_api_handlers()

# ── 页面配置 ──
st.set_page_config(
    page_title="多智能体议事厅",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

status_color = "#10b981" if api_ok else "#f59e0b"
status_text = "API已注册" if api_ok else "API未注册-使用本地模式"
st.markdown(
    f'<div style="text-align:center;padding:5px;background:{status_color};color:#000;font-size:12px;font-weight:700">'
    f'✅ v10 · {datetime.now().strftime("%Y-%m-%d %H:%M")} · {status_text}'
    '</div>',
    unsafe_allow_html=True,
)

# ── 加载并渲染前端 HTML ──
HTML_PATH = Path(__file__).parent / "frontend" / "index.html"
if not HTML_PATH.exists():
    st.error(f"Cannot find: {HTML_PATH}")
    st.stop()

html_content = HTML_PATH.read_text(encoding="utf-8")

# ── 运行时 CSS 修复 ──
html_content = html_content.replace(
    '.topic-input-row{display:flex;align-items:center;gap:6px;margin-bottom:8px}',
    '.topic-input-row{display:flex;align-items:center;gap:6px;margin-bottom:8px;flex-wrap:nowrap}'
)
html_content = html_content.replace(
    '.assign-status.error{color:var(--err)}',
    '.assign-status.error{color:var(--err)}.assign-status.done{color:#6ee7b7;font-size:9px}'
)

# ── 运行时 JS 修复：fetch 拦截器 ──
FETCH_FIX = """<script>
(function(){
  var _fetch=window.fetch;
  window.fetch=function(url,opts){
    return _fetch(url,opts).then(function(r){
      if(typeof url==='string'&&url.indexOf('/api/')>=0){
        var ct=r.headers.get('content-type')||'';
        if(!ct.includes('application/json')){throw new Error('API HTML response')}
      }
      return r;
    });
  };
})();
</script>
"""
html_content = html_content.replace('</head>', FETCH_FIX + '</head>')

st.components.v1.html(html_content, height=2000, scrolling=True)
