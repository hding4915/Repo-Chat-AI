import streamlit as st
import uuid
from ui.sidebar import render_sidebar
from ui.chat import render_chat
from core.storage import load_data, load_shared_chat

st.set_page_config(page_title="Repo Chat AI", page_icon="🦜", layout="wide")

# --- 0. 對話框裝飾器 ---
if hasattr(st, "dialog"):
    dialog_decorator = st.dialog
elif hasattr(st, "experimental_dialog"):
    dialog_decorator = st.experimental_dialog
else:
    def dialog_decorator(title):
        def decorator(func):
            def wrapper(*args, **kwargs):
                st.info(f"💡 {title}")
                with st.expander("點擊展開查看內容", expanded=True):
                    func(*args, **kwargs)

            return wrapper

        return decorator

# --- 1. 初始化資料 ---
loaded_repos, loaded_settings = load_data()

if "repos" not in st.session_state:
    st.session_state.repos = loaded_repos
if "api_key" not in st.session_state:
    st.session_state.api_key = loaded_settings.get("api_key", "")
if "ollama_url" not in st.session_state:
    st.session_state.ollama_url = loaded_settings.get("ollama_url", "http://192.168.0.210:11434")
if "base_url" not in st.session_state:
    st.session_state.base_url = loaded_settings.get("base_url", "http://localhost:8501")

if "current_repo_url" not in st.session_state:
    if st.session_state.repos:
        # --- 關鍵修改：啟動時選擇最近使用的 Repo ---
        sorted_repos = sorted(
            list(st.session_state.repos.keys()),
            key=lambda k: st.session_state.repos[k].get("last_accessed", 0),
            reverse=True
        )
        st.session_state.current_repo_url = sorted_repos[0]
    else:
        st.session_state.current_repo_url = None

if "qa_chain" not in st.session_state:
    st.session_state.qa_chain = None

# --- 2. 檢查是否為分享連結 ---
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
                    st.session_state.repos[repo_url] = {
                        "name": repo_name,
                        "threads": {},
                        "active_thread_id": None,
                        "last_accessed": 0  # 新匯入的先給個初始值
                    }

                new_thread_id = str(uuid.uuid4())[:8]
                st.session_state.repos[repo_url]["threads"][new_thread_id] = {
                    "title": f"(匯入) {shared_data['thread_title']}",
                    "messages": shared_data['messages']
                }

                st.session_state.current_repo_url = repo_url
                st.session_state.repos[repo_url]["active_thread_id"] = new_thread_id

                # 匯入後也算是一次「使用」，所以要存檔並更新時間
                import time
                st.session_state.repos[repo_url]["last_accessed"] = time.time()

                # 簡單的 save_current_state 邏輯 (因為無法直接 import ui.sidebar 的函式，這裡手動存)
                from core.storage import save_data
                settings = {
                    "api_key": st.session_state.api_key,
                    "ollama_url": st.session_state.ollama_url,
                    "base_url": st.session_state.base_url
                }
                save_data(st.session_state.repos, settings)

                st.query_params.clear()
                st.rerun()


        import_dialog()
    else:
        st.error("❌ 無效或已過期的分享連結")
        st.query_params.clear()

# --- 3. 正常渲染 ---
render_sidebar()
render_chat()