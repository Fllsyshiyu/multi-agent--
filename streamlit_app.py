"""
多智能体议事厅 · Streamlit 版 v9
所有修复（CSS + API 拦截）在运行时动态注入，不依赖 HTML 源文件是否更新。
"""

import streamlit as st
from pathlib import Path
from datetime import datetime

st.set_page_config(
    page_title="多智能体议事厅",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    '<div style="text-align:center;padding:5px;background:#10b981;color:#000;font-size:12px;font-weight:700">'
    '✅ v9 · ' + datetime.now().strftime('%Y-%m-%d %H:%M') + ' · 运行时注入修复'
    '</div>',
    unsafe_allow_html=True,
)

HTML_PATH = Path(__file__).parent / "frontend" / "index.html"
if not HTML_PATH.exists():
    st.error(f"Cannot find: {HTML_PATH}")
    st.stop()

html_content = HTML_PATH.read_text(encoding="utf-8")

# ── 运行时注入修复 1: CSS ──
html_content = html_content.replace(
    '.topic-input-row{display:flex;align-items:center;gap:6px;margin-bottom:8px}',
    '.topic-input-row{display:flex;align-items:center;gap:6px;margin-bottom:8px;flex-wrap:nowrap}'
)
html_content = html_content.replace(
    '.assign-status.error{color:var(--err)}',
    '.assign-status.error{color:var(--err)}.assign-status.done{color:#6ee7b7;font-size:9px}'
)

# ── 运行时注入修复 2: API 拦截 ──
# 在 iframe 中 fetch /api/* 返回 HTML（而非JSON）时自动降级到本地模式
FETCH_FIX = """<script>
(function(){
  var _fetch = window.fetch;
  window.fetch = function(url, opts) {
    return _fetch(url, opts).then(function(r) {
      var isApi = (typeof url === 'string') && url.indexOf('/api/') >= 0;
      if (isApi) {
        var ct = r.headers.get('content-type') || '';
        if (!ct.includes('application/json')) {
          var e = new Error('API returned HTML instead of JSON (Streamlit Cloud mode)');
          e.isApiHtml = true;
          throw e;
        }
      }
      return r;
    });
  };
})();
</script>
"""
html_content = html_content.replace('</head>', FETCH_FIX + '</head>')

# ── 运行时注入修复 3: 默认走本地模式 ──
# 页面加载时不自动调 API，直接走本地角色分配
SKIP_API = """<script>
window.STREAMLIT_CLOUD = true;
</script>
"""
html_content = html_content.replace('<body>', SKIP_API + '<body>')

st.components.v1.html(html_content, height=2000, scrolling=True)
