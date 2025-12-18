import os
import json
import uuid
import streamlit as st  # 引入 streamlit 以存取 secrets
from dotenv import load_dotenv
from core.config import HISTORY_FILE, SHARED_DIR


load_dotenv()


def get_config_value(key, default=""):
    try:
        if key in st.secrets:
            return st.secrets[key]
    except FileNotFoundError:
        pass
    except Exception:
        pass

    return os.getenv(key, default)


def load_data():
    env_settings = {
        "groq_api_key": get_config_value("GROQ_API_KEY"),
        "google_api_key": get_config_value("GOOGLE_API_KEY"),
        "api_key": get_config_value("MISTRAL_API_KEY"),  # Mistral

        "ollama_url": get_config_value("OLLAMA_LLM_URL", "http://localhost:11434"),

        "emb_api_key": get_config_value("OLLAMA_EMBEDDING_API_KEY"),
        "emb_ollama_url": get_config_value("OLLAMA_EMBEDDING_URL",
                                           get_config_value("OLLAMA_LLM_URL", "http://localhost:11434")),
    }

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