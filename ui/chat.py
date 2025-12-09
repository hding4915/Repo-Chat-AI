# ... (imports and helpers 保持不變) ...
import streamlit as st
import streamlit.components.v1 as components
from core.storage import save_data, save_shared_chat
from langchain_classic.callbacks.base import BaseCallbackHandler


# ... (StreamHandler, save_chat_history, convert_chat_to_markdown, dialog_decorator 保持不變) ...
# ... (render_scroll_button, share_dialog 保持不變) ...
# 為了節省篇幅，請保留前面的函式

class StreamHandler(BaseCallbackHandler):
    def __init__(self, container, initial_text=""):
        self.container = container
        self.text = initial_text

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.text += token
        self.container.markdown(self.text + "▌")


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


def render_scroll_button():
    scroll_js = """<script>(function(){try{var btnId="scroll-to-bottom-btn";var doc=window.parent.document;var existingBtn=doc.getElementById(btnId);if(existingBtn){existingBtn.remove();}var btn=doc.createElement("button");btn.id=btnId;btn.type="button";btn.innerHTML="⬇";btn.title="回到最新內容";btn.style.cssText=`position:fixed!important;bottom:120px!important;right:30px!important;z-index:2147483647!important;background-color:#262730!important;color:white!important;border:1px solid #4e4f55!important;border-radius:50%!important;width:45px!important;height:45px!important;font-size:20px!important;cursor:pointer!important;box-shadow:0px 4px 6px rgba(0,0,0,0.3)!important;display:none;align-items:center!important;justify-content:center!important;transition:opacity 0.3s,transform 0.2s!important;opacity:0!important;pointer-events:auto!important;`;btn.onmouseenter=function(){btn.style.transform="scale(1.1)";btn.style.backgroundColor="#3e404a";};btn.onmouseleave=function(){btn.style.transform="scale(1)";btn.style.backgroundColor="#262730";};function getMainContainer(){var container=doc.querySelector('[data-testid="stAppViewContainer"]');if(!container){container=doc.querySelector('.main');}return container;}btn.onclick=function(e){e.preventDefault();e.stopPropagation();var container=getMainContainer();if(container){container.scrollTo({top:container.scrollHeight,behavior:'smooth'});}};doc.body.appendChild(btn);function checkScroll(){var container=getMainContainer();if(!container)return;var distFromBottom=container.scrollHeight-container.scrollTop-container.clientHeight;if(container.scrollHeight>container.clientHeight&&distFromBottom>300){if(btn.style.display!=="flex"){btn.style.display="flex";requestAnimationFrame(()=>{btn.style.opacity="1";});}}else{if(btn.style.opacity!=="0"){btn.style.setProperty("opacity","0","important");setTimeout(()=>{if(btn.style.opacity==="0")btn.style.display="none";},300);}}}setInterval(checkScroll,500);var container=getMainContainer();if(container){container.addEventListener("scroll",checkScroll);}}catch(e){console.error("Scroll button error:",e);}})();</script>"""
    components.html(scroll_js, height=0, width=0)


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
        with st.chat_message(msg["role"]): st.markdown(msg["content"])

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

                    # --- 關鍵修改：準備 Embedding Config ---
                    emb_config = {
                        "provider": st.session_state.get("emb_provider", "Ollama"),
                        "model": st.session_state.get("emb_model", "nomic-embed-text"),
                        "api_key": st.session_state.get("emb_api_key", ""),
                        "base_url": st.session_state.get("ollama_url", "http://localhost:11434")
                    }

                    st.session_state.qa_chain = get_qa_chain(current_url, st.session_state.api_key,
                                                             st.session_state.ollama_url, embedding_config=emb_config)

                if st.session_state.qa_chain:
                    response = st.session_state.qa_chain.invoke(
                        {"question": prompt},
                        config={"callbacks": [stream_handler]}
                    )
                    answer = response["answer"]
                    message_placeholder.markdown(answer)
                    messages.append({"role": "assistant", "content": answer})
                    save_chat_history()
                    if is_first_message: st.rerun()
                else:
                    message_placeholder.error("❌ Chain 初始化失敗")
            except Exception as e:
                message_placeholder.error(f"發生錯誤: {e}")
                print(response)
                if messages and messages[-1]["role"] == "user": messages.pop()

    render_scroll_button()