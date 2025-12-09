import streamlit as st

# --- ☁️ Streamlit Cloud 部署專用修正 ---
try:
    __import__('pysqlite3')
    import sys
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass
# ------------------------------------

import uuid
from ui.sidebar import render_sidebar
from ui.chat import render_chat
from core.storage import load_data, load_shared_chat

st.set_page_config(page_title="Repo Chat AI", page_icon="🦜", layout="wide")

if hasattr(st, "dialog"): dialog_decorator = st.dialog
elif hasattr(st, "experimental_dialog"): dialog_decorator = st.experimental_dialog
else:
    def dialog_decorator(title):
        def decorator(func):
            def wrapper(*args, **kwargs):
                st.info(f"💡 {title}")
                with st.expander(f"✨ {title}", expanded=True): func(*args, **kwargs)
            return wrapper
        return decorator

# --- 1. 初始化資料 ---
loaded_repos, loaded_settings = load_data()

if "repos" not in st.session_state: st.session_state.repos = loaded_repos

# --- 初始化 Settings (包含新的 Env Vars) ---
# 使用 setdefault 確保有預設值
st.session_state.setdefault("api_key", loaded_settings.get("api_key", ""))
st.session_state.setdefault("ollama_url", loaded_settings.get("ollama_url", "http://localhost:11434"))
st.session_state.setdefault("base_url", loaded_settings.get("base_url", "http://localhost:8501"))

# Providers & Models
st.session_state.setdefault("llm_provider", loaded_settings.get("llm_provider", "Mistral AI"))
st.session_state.setdefault("mistral_model", loaded_settings.get("mistral_model", "codestral-latest"))
st.session_state.setdefault("google_api_key", loaded_settings.get("google_api_key", ""))
st.session_state.setdefault("google_model", loaded_settings.get("google_model", "gemini-pro"))
st.session_state.setdefault("groq_api_key", loaded_settings.get("groq_api_key", ""))
st.session_state.setdefault("groq_model", loaded_settings.get("groq_model", "llama3-70b-8192"))
st.session_state.setdefault("ollama_model", loaded_settings.get("ollama_model", "llama3"))

# Embedding Settings
st.session_state.setdefault("emb_provider", loaded_settings.get("emb_provider", "Ollama"))
st.session_state.setdefault("emb_model", loaded_settings.get("emb_model", "nomic-embed-text"))
st.session_state.setdefault("emb_api_key", loaded_settings.get("emb_api_key", ""))
st.session_state.setdefault("emb_ollama_url", loaded_settings.get("emb_ollama_url", "http://localhost:11434"))

if "current_repo_url" not in st.session_state:
    if st.session_state.repos:
        sorted_repos = sorted(list(st.session_state.repos.keys()), key=lambda k: st.session_state.repos[k].get("last_accessed", 0), reverse=True)
        st.session_state.current_repo_url = sorted_repos[0]
    else:
        st.session_state.current_repo_url = None

if "qa_chain" not in st.session_state:
    st.session_state.qa_chain = None

# --- 2. 檢查分享連結 ---
query_params = st.query_params
share_id = query_params.get("share_id")

if share_id:
    shared_data = load_shared_chat(share_id)
    if shared_data:
        st.toast("🔗 偵測到分享連結！", icon="🎁")
        @dialog_decorator("🎁 匯入分享對話")
        def import_dialog():
            st.markdown(f"### 標題: {shared_data['thread_title']}")
            st.markdown(f"**來源專案**: `{shared_data['repo_name']}`")
            st.caption(f"原始 URL: {shared_data['repo_url']}")
            st.info("匯入後，您可以在自己的電腦上繼續這段對話。")
            if st.button("📥 匯入至我的對話", type="primary", use_container_width=True):
                repo_url = shared_data['repo_url']
                repo_name = shared_data['repo_name']
                if repo_url not in st.session_state.repos:
                    st.session_state.repos[repo_url] = { "name": repo_name, "threads": {}, "active_thread_id": None, "last_accessed": 0 }
                new_thread_id = str(uuid.uuid4())[:8]
                st.session_state.repos[repo_url]["threads"][new_thread_id] = { "title": f"(匯入) {shared_data['thread_title']}", "messages": shared_data['messages'] }
                st.session_state.current_repo_url = repo_url
                st.session_state.repos[repo_url]["active_thread_id"] = new_thread_id
                import time
                st.session_state.repos[repo_url]["last_accessed"] = time.time()
                from core.storage import save_data
                # 重新打包 settings 存檔，避免覆蓋掉新載入的 env vars
                current_settings = {k: st.session_state.get(k) for k in loaded_settings.keys()}
                save_data(st.session_state.repos, current_settings)
                st.query_params.clear()
                st.rerun()
        import_dialog()
    else:
        st.error("❌ 無效或已過期的分享連結")
        st.query_params.clear()

render_sidebar()
render_chat()