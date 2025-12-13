import streamlit as st
import streamlit.components.v1 as components
from core.storage import save_data, save_shared_chat
from langchain_classic.callbacks.base import BaseCallbackHandler


# --- 1. 定義 StreamHandler ---
class StreamHandler(BaseCallbackHandler):
    def __init__(self, container, initial_text=""):
        self.container = container
        self.text = initial_text

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.text += token
        self.container.markdown(self.text + "▌")


# --- 2. 存檔 helper ---
def save_chat_history():
    settings = {
        "api_key": st.session_state.api_key,
        "ollama_url": st.session_state.ollama_url,
        "base_url": st.session_state.base_url
    }
    save_data(st.session_state.repos, settings)


def convert_chat_to_markdown(title, messages, repo_name):
    md_content = f"# 🦜 Repo Chat: {title}\n\n**Repository:** `{repo_name}`\n---\n\n"
    for msg in messages:
        role_icon = "👤" if msg["role"] == "user" else "🤖"
        md_content += f"### {role_icon} {msg['role'].upper()}\n\n{msg['content']}\n\n"
        if msg["role"] == "assistant": md_content += "---\n\n"
    return md_content


# --- 3. 對話框裝飾器 ---
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


# --- 4. JS 注入: 回到底部按鈕 ---
def render_scroll_button():
    """
    注入 JavaScript 以建立一個懸浮按鈕。
    修正版：調整位置、增加 Z-Index、並加入除錯用的強制顯示邏輯。
    """
    scroll_js = """
    <script>
        (function() {
            var btnId = "scroll-to-bottom-btn";

            function createBtn() {
                var doc = window.parent.document;

                if (doc.getElementById(btnId)) {
                    return doc.getElementById(btnId);
                }

                var btn = doc.createElement("button");
                btn.id = btnId;
                btn.innerHTML = "⬇";
                btn.title = "回到最新內容";

                btn.style.cssText = `
                    position: fixed !important;
                    bottom: 150px !important;
                    right: 30px !important;
                    z-index: 2147483647 !important;
                    background-color: #4CAF50 !important;
                    color: white !important;
                    border: none !important;
                    border-radius: 50% !important;
                    width: 50px !important;
                    height: 50px !important;
                    font-size: 24px !important;
                    cursor: pointer !important;
                    box-shadow: 0px 4px 12px rgba(0,0,0,0.5) !important;
                    display: flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    transition: opacity 0.3s, transform 0.2s !important;
                    opacity: 0 !important;
                    pointer-events: auto !important;
                `;

                btn.onclick = function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    var container = getScrollContainer();
                    if (container) {
                        container.scrollTo({
                            top: container.scrollHeight,
                            behavior: 'smooth'
                        });
                    }
                };

                btn.onmouseenter = function() { btn.style.transform = "scale(1.1)"; };
                btn.onmouseleave = function() { btn.style.transform = "scale(1)"; };

                doc.body.appendChild(btn);
                return btn;
            }

            function getScrollContainer() {
                var doc = window.parent.document;
                var candidates = [
                    '[data-testid="stAppViewContainer"]',
                    '.main',
                    'section[tabindex="0"]'
                ];

                for (var i = 0; i < candidates.length; i++) {
                    var el = doc.querySelector(candidates[i]);
                    if (el && el.scrollHeight > el.clientHeight) {
                        return el;
                    }
                }
                return doc.body;
            }

            function checkScroll() {
                var btn = createBtn();
                var container = getScrollContainer();

                if (!container) return;

                if (container.scrollHeight <= container.clientHeight) {
                    btn.style.opacity = "0";
                    btn.style.pointerEvents = "none";
                    return;
                }

                var dist = container.scrollHeight - container.scrollTop - container.clientHeight;

                if (dist > 100) {
                    btn.style.opacity = "1";
                    btn.style.pointerEvents = "auto";
                } else {
                    btn.style.opacity = "0";
                    btn.style.pointerEvents = "none";
                }
            }

            setInterval(checkScroll, 500);

            var container = getScrollContainer();
            if (container) {
                container.addEventListener("scroll", checkScroll);
            }

            var btn = createBtn();
            btn.style.opacity = "1";
            setTimeout(() => { checkScroll(); }, 2000);

        })();
    </script>
    """
    components.html(scroll_js, height=0, width=0)


# --- Share Dialog 函式 ---
@dialog_decorator("🔗 分享對話")
def share_dialog(repo_url, repo_name, current_thread):
    st.markdown("正在建立公開連結...")
    share_id = save_shared_chat(repo_url, repo_name, current_thread)
    if share_id:
        base = st.session_state.base_url.rstrip("/") if st.session_state.base_url else "http://localhost:8501"
        share_link = f"{base}/?share_id={share_id}"
        st.success("連結建立成功！")
        st.code(share_link, language="text")
    else:
        st.error("建立失敗")


def render_chat():
    current_url = st.session_state.current_repo_url
    if not current_url or current_url not in st.session_state.repos:
        st.markdown(
            "<div style='text-align: center; margin-top: 50px; color: gray;'><h1>🦜 Repo Chat</h1><p>👈 請在左側選擇或新增一個專案來開始。</p></div>",
            unsafe_allow_html=True)
        return

    repo_data = st.session_state.repos[current_url]
    active_thread_id = repo_data.get("active_thread_id")
    if not active_thread_id or active_thread_id not in repo_data["threads"]:
        st.warning("請選擇一個對話串")
        return

    current_thread = repo_data["threads"][active_thread_id]
    messages = current_thread["messages"]
    repo_name = repo_data['name']
    chat_title = current_thread['title']

    st.caption(f"📍 {repo_name} / {chat_title}")

    for msg in messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if "sources" in msg:
                with st.expander("📚 參考文件來源 (已存檔)", expanded=False):
                    for source in msg["sources"]:
                        st.caption(f"📄 `{source}`")

    if prompt := st.chat_input("請問關於這個程式碼的問題..."):
        is_first_message = (len(messages) == 0)
        if is_first_message:
            safe_title = prompt[:50] + "..." if len(prompt) > 50 else prompt
            current_thread["title"] = safe_title

        with st.chat_message("user"):
            st.markdown(prompt)
        messages.append({"role": "user", "content": prompt})
        save_chat_history()

        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            message_placeholder.markdown("🤖 *思考中，正在翻閱程式碼...*")
            stream_handler = StreamHandler(message_placeholder)

            try:
                if not st.session_state.qa_chain:
                    from core.rag import get_qa_chain
                    emb_config = {
                        "provider": st.session_state.get("emb_provider", "Ollama"),
                        "model": st.session_state.get("emb_model", "nomic-embed-text"),
                        "api_key": st.session_state.get("emb_api_key", ""),
                        "base_url": st.session_state.get("emb_ollama_url") or st.session_state.get("ollama_url",
                                                                                                   "http://localhost:11434")
                    }
                    st.session_state.qa_chain = get_qa_chain(current_url, st.session_state.api_key,
                                                             st.session_state.ollama_url, embedding_config=emb_config)

                if st.session_state.qa_chain:
                    response = st.session_state.qa_chain.invoke(
                        {"question": prompt},
                        config={"callbacks": [stream_handler]}
                    )
                    answer = response["answer"]
                    source_docs = response.get("source_documents", [])
                    message_placeholder.markdown(answer)

                    sources_list = []
                    if source_docs:
                        with st.expander("📚 參考文件來源", expanded=False):
                            # --- 關鍵修正：去重邏輯 ---
                            seen_sources = set()
                            for doc in source_docs:
                                source_name = doc.metadata.get("source", "Unknown File")
                                # 只有當這個檔名還沒出現過時，才顯示並加入列表
                                if source_name not in seen_sources:
                                    st.caption(f"📄 `{source_name}`")
                                    seen_sources.add(source_name)
                                    sources_list.append(source_name)

                    messages.append({
                        "role": "assistant",
                        "content": answer,
                        "sources": sources_list
                    })
                    save_chat_history()
                    if is_first_message: st.rerun()
                else:
                    message_placeholder.error("❌ Chain 初始化失敗")
            except Exception as e:
                message_placeholder.error(f"發生錯誤: {e}")
                if messages and messages[-1]["role"] == "user": messages.pop()

    render_scroll_button()