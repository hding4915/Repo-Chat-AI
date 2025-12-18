import streamlit as st
import uuid
import time
from core.ingestion import ingest_repo, remove_repo_data
from core.rag import get_qa_chain
from core.storage import save_data, save_shared_chat


def inject_custom_css():
    st.markdown("""
        <style>
            section[data-testid="stSidebar"] { min-width: 350px !important; width: 350px !important; }
            section[data-testid="stSidebar"] .stButton button { text-align: left; justify-content: flex-start; padding-left: 0.5rem !important; padding-right: 0.5rem !important; border: 1px solid transparent; background-color: transparent; color: inherit; transition: background-color 0.2s; white-space: nowrap !important; overflow: hidden !important; text-overflow: ellipsis !important; width: 100% !important; display: flex !important; align-items: center !important; }
            section[data-testid="stSidebar"] .stButton button p, section[data-testid="stSidebar"] .stButton button div { white-space: nowrap !important; overflow: hidden !important; text-overflow: ellipsis !important; display: inline-block !important; }
            section[data-testid="stSidebar"] .stButton button:hover { border: 1px solid rgba(128, 128, 128, 0.2); background-color: rgba(128, 128, 128, 0.1); }
            div[data-testid="stVerticalBlock"] > div > button[kind="primary"] { background-color: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 20px; text-align: left; padding-left: 1rem !important; }
            div[data-testid="stPopover"] button { text-align: center !important; justify-content: center !important; padding-left: 0 !important; border: none !important; }
            div[data-testid="stPopover"] button:hover { background-color: rgba(128, 128, 128, 0.1) !important; }
            div[data-testid="stPopoverBody"] .stButton button, div[data-testid="stPopoverBody"] .stDownloadButton button { border: none !important; background: transparent !important; text-align: left !important; justify-content: flex-start !important; padding: 0.5rem 1rem !important; width: 100% !important; border-radius: 4px !important; color: inherit !important; font-weight: normal !important; display: flex !important; }
            div[data-testid="stPopoverBody"] .stButton button:hover, div[data-testid="stPopoverBody"] .stDownloadButton button:hover { background-color: rgba(128, 128, 128, 0.1) !important; color: inherit !important; }
            div[data-testid="stPopoverBody"] hr { margin: 0.5rem 0 !important; }
        </style>
    """, unsafe_allow_html=True)


# ... (Helper functions: save_current_state, create_new_thread, delete_thread, rename_thread, convert_chat_to_markdown, dialogs, handle_delete_repo 保持不變，為了節省篇幅省略，請務必保留) ...
def save_current_state():
    settings = {
        "api_key": st.session_state.api_key,
        "ollama_url": st.session_state.ollama_url,
        "base_url": st.session_state.base_url,
        "emb_provider": st.session_state.get("emb_provider", "Ollama"),
        "emb_model": st.session_state.get("emb_model", "nomic-embed-text"),
        "emb_api_key": st.session_state.get("emb_api_key", ""),
        "emb_ollama_url": st.session_state.get("emb_ollama_url", "http://localhost:11434"),
        "llm_provider": st.session_state.get("llm_provider", "Mistral AI"),
        "mistral_model": st.session_state.get("mistral_model", "codestral-latest"),
        "google_api_key": st.session_state.get("google_api_key", ""),
        "google_model": st.session_state.get("google_model", "gemini-pro"),
        "groq_api_key": st.session_state.get("groq_api_key", ""),
        "groq_model": st.session_state.get("groq_model", "llama3-70b-8192"),
        "ollama_model": st.session_state.get("ollama_model", "llama3"),
    }
    save_data(st.session_state.repos, settings)


def create_new_thread(repo_url, thread_title="新對話"):
    thread_id = str(uuid.uuid4())[:8]
    st.session_state.repos[repo_url]["threads"][thread_id] = {"title": thread_title, "messages": []}
    st.session_state.repos[repo_url]["active_thread_id"] = thread_id
    st.session_state.repos[repo_url]["last_accessed"] = time.time()
    save_current_state()
    return thread_id


def delete_thread(repo_url, thread_id):
    if thread_id in st.session_state.repos[repo_url]["threads"]:
        del st.session_state.repos[repo_url]["threads"][thread_id]
        if st.session_state.repos[repo_url]["active_thread_id"] == thread_id:
            remaining = list(st.session_state.repos[repo_url]["threads"].keys())
            st.session_state.repos[repo_url]["active_thread_id"] = remaining[0] if remaining else None
        st.session_state.repos[repo_url]["last_accessed"] = time.time()
        save_current_state()
        st.rerun()


def rename_thread(repo_url, thread_id, new_title):
    if repo_url in st.session_state.repos and thread_id in st.session_state.repos[repo_url]["threads"]:
        st.session_state.repos[repo_url]["threads"][thread_id]["title"] = new_title
        save_current_state()
        st.rerun()


def convert_chat_to_markdown(title, messages, repo_name):
    md_content = f"# 🦜 Repo Chat: {title}\n\n**Repository:** `{repo_name}`\n---\n\n"
    for msg in messages:
        role_icon = "👤" if msg["role"] == "user" else "🤖"
        md_content += f"### {role_icon} {msg['role'].upper()}\n\n{msg['content']}\n\n"
        if msg["role"] == "assistant": md_content += "---\n\n"
    return md_content


if hasattr(st, "dialog"):
    dialog_decorator = st.dialog
elif hasattr(st, "experimental_dialog"):
    dialog_decorator = st.experimental_dialog
else:
    def dialog_decorator(title):
        def decorator(func):
            def wrapper(*args, **kwargs):
                with st.expander(f"✨ {title}", expanded=True): func(*args, **kwargs)

            return wrapper

        return decorator


@dialog_decorator("🔗 分享對話")
def sidebar_share_dialog(repo_url, repo_name, current_thread):
    st.markdown("正在建立公開連結...")
    share_id = save_shared_chat(repo_url, repo_name, current_thread)
    if share_id:
        base = st.session_state.base_url.rstrip("/") if st.session_state.base_url else "http://localhost:8501"
        share_link = f"{base}/?share_id={share_id}"
        st.success("連結建立成功！")
        st.code(share_link, language="text")
    else:
        st.error("建立失敗")


@dialog_decorator("✏️ 重新命名")
def sidebar_rename_dialog(repo_url, thread_id, current_title):
    new_title = st.text_input("輸入新名稱", value=current_title)
    if st.button("確認修改", type="primary", use_container_width=True):
        rename_thread(repo_url, thread_id, new_title)
        st.rerun()


@dialog_decorator("🗑️ 刪除對話")
def sidebar_delete_dialog(repo_url, thread_id, title):
    st.warning(f"確定要刪除「{title}」嗎？")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("確認刪除", type="primary", use_container_width=True):
            delete_thread(repo_url, thread_id)
            st.rerun()
    with col2:
        if st.button("取消", use_container_width=True): st.rerun()


def handle_delete_repo(repo_url):
    remove_repo_data(repo_url)
    if repo_url in st.session_state.repos: del st.session_state.repos[repo_url]
    if st.session_state.current_repo_url == repo_url:
        remaining = sorted(list(st.session_state.repos.keys()),
                           key=lambda k: st.session_state.repos[k].get("last_accessed", 0), reverse=True)
        st.session_state.current_repo_url = remaining[0] if remaining else None
        st.session_state.qa_chain = None
    save_current_state()
    st.toast("🗑️ 專案已刪除", icon="✅")
    time.sleep(1)
    st.rerun()


def render_add_repo_ui():
    st.markdown("#### Clone 新專案")

    # 更新提示，讓使用者知道可以貼 SSH
    new_repo_url = st.text_input(
        "GitHub URL",
        placeholder="https://... 或 git@github.com:...",
        help="支援公開 HTTPS 網址，或私有倉庫的 SSH 網址 (需在本地配置 SSH Key)"
    )

    if st.button("載入 Repo", type="primary", use_container_width=True, key="btn_load_repo"):
        if not new_repo_url:
            st.error("網址不能為空")
        else:
            process_repo(new_repo_url)


def render_sidebar():
    inject_custom_css()
    with st.sidebar:
        if not st.session_state.repos:
            st.info("👈 請先 Clone 一個專案")
            with st.popover("➕ Clone 新專案", use_container_width=True): render_add_repo_ui()
            render_settings()
            return

        repo_options = sorted(list(st.session_state.repos.keys()),
                              key=lambda k: st.session_state.repos[k].get("last_accessed", 0), reverse=True)

        def get_repo_name(url):
            return st.session_state.repos[url]["name"]

        current_index = 0
        if st.session_state.current_repo_url in repo_options: current_index = repo_options.index(
            st.session_state.current_repo_url)
        selected_repo_url = st.selectbox("切換專案", options=repo_options, index=current_index,
                                         format_func=get_repo_name, label_visibility="collapsed")

        if selected_repo_url != st.session_state.current_repo_url:
            st.session_state.current_repo_url = selected_repo_url
            st.session_state.qa_chain = None
            st.session_state.repos[selected_repo_url]["last_accessed"] = time.time()
            save_current_state()
            st.rerun()

        repo_data = st.session_state.repos[selected_repo_url]
        col_add, col_manage = st.columns([1, 1])
        with col_add:
            with st.popover("➕ 新增", help="Clone 新專案", use_container_width=True): render_add_repo_ui()
        with col_manage:
            with st.popover("⚙️ 管理", help="管理此專案", use_container_width=True):
                st.markdown("#### 專案操作")
                if st.button("🔄 更新同步", help="檢查 Git 更新", use_container_width=True): process_repo(
                    selected_repo_url, force=False)
                st.divider()
                st.markdown("#### 危險區域")
                if st.button("🗑️ 刪除專案", type="primary", use_container_width=True): handle_delete_repo(
                    selected_repo_url)

        st.markdown("---")
        if st.button("✨ 開啟新對話", type="primary", use_container_width=True):
            create_new_thread(selected_repo_url)
            st.rerun()

        st.caption("近期對話")
        thread_ids = list(repo_data["threads"].keys())[::-1]
        if not thread_ids: st.caption("尚無紀錄")

        for t_id in thread_ids:
            thread = repo_data["threads"][t_id]
            is_active = (repo_data["active_thread_id"] == t_id)
            c_main, c_menu = st.columns([5, 1])
            with c_main:
                prefix = "● " if is_active else ""
                full_title = thread['title']
                display_label = full_title[:14] + "..." if len(full_title) > 14 else full_title
                if st.button(f"{prefix}{display_label}", key=f"th_{t_id}", help=full_title,
                             use_container_width=True): switch_thread(selected_repo_url, t_id)
            with c_menu:
                with st.popover("⋮", use_container_width=True):
                    if st.button("🔗 共用", key=f"share_{t_id}", use_container_width=True): sidebar_share_dialog(
                        selected_repo_url, repo_data["name"], thread)
                    md_text = convert_chat_to_markdown(thread['title'], thread['messages'], repo_data["name"])
                    st.download_button(label="📤 匯出", data=md_text, file_name=f"chat_{t_id}.md", mime="text/markdown",
                                       key=f"export_{t_id}", use_container_width=True)
                    if st.button("✏️ 重新命名", key=f"ren_btn_{t_id}", use_container_width=True): sidebar_rename_dialog(
                        selected_repo_url, t_id, thread['title'])
                    st.divider()
                    if st.button("🗑️ 刪除", key=f"del_{t_id}", use_container_width=True): sidebar_delete_dialog(
                        selected_repo_url, t_id, thread['title'])

        st.markdown("<br>" * 2, unsafe_allow_html=True)
        render_settings()


def render_settings():
    with st.expander("⚙️ 系統設定"):
        st.markdown("#### 🧠 Embedding 設定")
        emb_providers = ["Ollama", "OpenAI", "Mistral AI"]
        current_emb_provider = st.session_state.get("emb_provider", "Ollama")

        selected_emb_provider = st.selectbox(
            "Embedding 來源",
            emb_providers,
            index=emb_providers.index(current_emb_provider) if current_emb_provider in emb_providers else 0,
            key="input_emb_provider",
            on_change=update_settings
        )

        if selected_emb_provider == "Ollama":
            st.text_input("Model", value=st.session_state.get("emb_model", "nomic-embed-text"), key="input_emb_model",
                          on_change=update_settings)
            st.text_input("Embedding Ollama URL",
                          value=st.session_state.get("emb_ollama_url", "http://localhost:11434"),
                          key="input_emb_ollama_url", on_change=update_settings)
            st.text_input("Ollama API Key", value=st.session_state.get("emb_api_key", ""), type="password",
                          key="input_emb_api_key", on_change=update_settings)

        elif selected_emb_provider == "OpenAI":
            st.text_input("API Key", value=st.session_state.get("emb_api_key", ""), type="password",
                          key="input_emb_api_key", on_change=update_settings)
            st.text_input("Model", value=st.session_state.get("emb_model", "text-embedding-3-small"),
                          key="input_emb_model", on_change=update_settings)
        elif selected_emb_provider == "Mistral AI":
            st.text_input("API Key", value=st.session_state.get("emb_api_key", ""), type="password",
                          key="input_emb_api_key", on_change=update_settings)
            st.text_input("Model", value=st.session_state.get("emb_model", "mistral-embed"), key="input_emb_model",
                          on_change=update_settings)

        st.divider()
        st.markdown("#### 💬 Chat Model 設定")
        providers = ["Mistral AI", "Google Gemini", "Groq", "Ollama"]
        current_provider = st.session_state.get("llm_provider", "Mistral AI")
        if current_provider not in providers: current_provider = "Mistral AI"

        selected_provider = st.selectbox(
            "Chat 來源",
            providers,
            index=providers.index(current_provider),
            key="input_llm_provider",
            on_change=update_settings
        )

        if selected_provider == "Mistral AI":
            st.text_input("Mistral API Key", value=st.session_state.get("api_key", ""), type="password",
                          key="input_api_key", on_change=update_settings)
            st.text_input("Model Name", value=st.session_state.get("mistral_model", "codestral-latest"),
                          key="input_mistral_model", on_change=update_settings)
        elif selected_provider == "Google Gemini":
            st.text_input("Google API Key", value=st.session_state.get("google_api_key", ""), type="password",
                          key="input_google_api_key", on_change=update_settings)
            st.text_input("Model Name", value=st.session_state.get("google_model", "gemini-pro"),
                          key="input_google_model", on_change=update_settings)
        elif selected_provider == "Groq":
            st.text_input("Groq API Key", value=st.session_state.get("groq_api_key", ""), type="password",
                          key="input_groq_api_key", on_change=update_settings)
            st.text_input("Model Name", value=st.session_state.get("groq_model", "llama3-70b-8192"),
                          key="input_groq_model", on_change=update_settings)
        elif selected_provider == "Ollama":
            st.text_input("Model Name", value=st.session_state.get("ollama_model", "llama3"), key="input_ollama_model",
                          on_change=update_settings)

        st.divider()
        st.markdown("#### 🏗️ 基礎設施")
        st.text_input("Ollama URL (Chat Default)", value=st.session_state.get("ollama_url", "http://localhost:11434"),
                      key="input_ollama_url", on_change=update_settings)
        st.text_input("網站公開網址 (Base URL)", value=st.session_state.get("base_url", ""),
                      placeholder="例如: https://hding49.uk", key="input_base_url", on_change=update_settings)
        st.caption("v2.13.0 | Repo Chat AI")


def update_settings():
    if "input_emb_provider" in st.session_state: st.session_state.emb_provider = st.session_state.input_emb_provider
    if "input_emb_model" in st.session_state: st.session_state.emb_model = st.session_state.input_emb_model
    if "input_emb_api_key" in st.session_state: st.session_state.emb_api_key = st.session_state.input_emb_api_key
    if "input_emb_ollama_url" in st.session_state: st.session_state.emb_ollama_url = st.session_state.input_emb_ollama_url

    if "input_llm_provider" in st.session_state: st.session_state.llm_provider = st.session_state.input_llm_provider
    if "input_ollama_url" in st.session_state: st.session_state.ollama_url = st.session_state.input_ollama_url
    if "input_base_url" in st.session_state: st.session_state.base_url = st.session_state.input_base_url

    if "input_api_key" in st.session_state: st.session_state.api_key = st.session_state.input_api_key
    if "input_mistral_model" in st.session_state: st.session_state.mistral_model = st.session_state.input_mistral_model
    if "input_google_api_key" in st.session_state: st.session_state.google_api_key = st.session_state.input_google_api_key
    if "input_google_model" in st.session_state: st.session_state.google_model = st.session_state.input_google_model
    if "input_groq_api_key" in st.session_state: st.session_state.groq_api_key = st.session_state.input_groq_api_key
    if "input_groq_model" in st.session_state: st.session_state.groq_model = st.session_state.input_groq_model
    if "input_ollama_model" in st.session_state: st.session_state.ollama_model = st.session_state.input_ollama_model

    save_current_state()


def process_repo(url, force=False):
    status_container = st.status("🚀 正在連線與處理...", expanded=True)
    p_bar = status_container.progress(0)
    msg_placeholder = status_container.empty()
    try:
        def update_progress(msg, p):
            p_bar.progress(max(0, min(100, p)))
            msg_placeholder.code(msg, language="text")

        embedding_config = {
            "provider": st.session_state.get("emb_provider", "Ollama"),
            "model": st.session_state.get("emb_model", "nomic-embed-text"),
            "api_key": st.session_state.get("emb_api_key", ""),
            "base_url": st.session_state.get("emb_ollama_url") or st.session_state.get("ollama_url",
                                                                                       "http://localhost:11434")
        }

        _, status = ingest_repo(url, update_progress, force_update=force, embedding_config=embedding_config)

        if url not in st.session_state.repos:
            st.session_state.repos[url] = {"name": url.rstrip("/").split("/")[-1], "threads": {},
                                           "active_thread_id": None, "last_accessed": time.time()}
            create_new_thread(url, "Default Chat")
        else:
            st.session_state.repos[url]["last_accessed"] = time.time()
            save_current_state()

        if status == "skipped":
            status_container.update(label="⚡ 快取載入成功！", state="complete", expanded=False)
        else:
            status_container.update(label="✅ 專案載入完成！", state="complete", expanded=False)
        st.session_state.current_repo_url = url
        time.sleep(1)
        st.rerun()
    except Exception as e:
        status_container.update(label="❌ 處理失敗", state="error", expanded=True)
        st.error(f"詳細錯誤: {e}")


def switch_thread(repo_url, thread_id):
    st.session_state.current_repo_url = repo_url
    st.session_state.repos[repo_url]["active_thread_id"] = thread_id
    st.session_state.qa_chain = None
    st.session_state.repos[repo_url]["last_accessed"] = time.time()
    save_current_state()
    st.rerun()