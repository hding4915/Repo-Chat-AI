import os
import json
import uuid
import streamlit as st  # 引入 streamlit 以存取 secrets
from dotenv import load_dotenv
from core.config import HISTORY_FILE, SHARED_DIR

# 載入本地 .env (如果有的話)
load_dotenv()


def get_config_value(key, default=""):
    """
    統一設定讀取器：
    1. 嘗試從 Streamlit Secrets 讀取 (Cloud 部署用)
    2. 嘗試從 os.getenv 讀取 (本地 .env 用)
    3. 回傳預設值
    """
    # 1. 檢查 st.secrets (Streamlit Cloud)
    # st.secrets 像一個字典，如果沒設定會拋出 KeyError，所以要用 try-catch 或 get
    try:
        if key in st.secrets:
            return st.secrets[key]
    except FileNotFoundError:
        pass  # 本地沒有 secrets.toml 是正常的
    except Exception:
        pass

        # 2. 檢查 Environment Variable (Local .env)
    return os.getenv(key, default)


def load_data():
    """
    載入順序：
    1. 程式預設值 (Env/Secrets)
    2. 使用者手動設定 (JSON) -> 覆蓋預設值
    """

    # 從 Secrets/Env 讀取「系統預設值」
    env_settings = {
        "groq_api_key": get_config_value("GROQ_API_KEY"),
        "google_api_key": get_config_value("GOOGLE_API_KEY"),
        "api_key": get_config_value("MISTRAL_API_KEY"),  # Mistral

        # Ollama 設定
        "ollama_url": get_config_value("OLLAMA_LLM_URL", "http://localhost:11434"),

        # Embedding 設定
        "emb_api_key": get_config_value("OLLAMA_EMBEDDING_API_KEY"),
        "emb_ollama_url": get_config_value("OLLAMA_EMBEDDING_URL",
                                           get_config_value("OLLAMA_LLM_URL", "http://localhost:11434")),
    }

    # 嘗試讀取使用者的手動設定 (history.json)
    json_repos = {}
    json_settings = {}

    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                json_repos = data.get("repos", {})
                json_settings = data.get("settings", {})
        except Exception as e:
            print(f"讀取歷史失敗: {e}")

    # 合併設定：以 Env 為基底，被 JSON 覆蓋
    final_settings = env_settings.copy()
    for key, value in json_settings.items():
        final_settings[key] = value

    return json_repos, final_settings


def save_data(repos, settings):
    data = {
        "repos": repos,
        "settings": settings
    }
    try:
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"儲存歷史失敗: {e}")


def save_shared_chat(repo_url, repo_name, thread_data):
    share_id = str(uuid.uuid4())
    file_path = os.path.join(SHARED_DIR, f"{share_id}.json")

    # 嘗試 import time，防止有些環境沒 import
    import time
    created_at = str(time.time())

    share_content = {
        "share_id": share_id,
        "repo_url": repo_url,
        "repo_name": repo_name,
        "thread_title": thread_data.get("title", "未命名對話"),
        "messages": thread_data.get("messages", []),
        "created_at": created_at
    }

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(share_content, f, ensure_ascii=False, indent=2)
        return share_id
    except Exception as e:
        print(f"分享失敗: {e}")
        return None


def load_shared_chat(share_id):
    file_path = os.path.join(SHARED_DIR, f"{share_id}.json")
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None