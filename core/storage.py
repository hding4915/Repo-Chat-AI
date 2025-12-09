import os
import json
import uuid
from core.config import HISTORY_FILE, SHARED_DIR  # 引入新路徑


def load_data():
    if not os.path.exists(HISTORY_FILE):
        return {}, {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            repos = data.get("repos", {})
            settings = data.get("settings", {})
            return repos, settings
    except Exception as e:
        print(f"讀取歷史失敗: {e}")
        return {}, {}


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


# --- 新增功能：分享機制 ---

def save_shared_chat(repo_url, repo_name, thread_data):
    """
    將特定對話儲存為分享檔案
    回傳: share_id (UUID)
    """
    share_id = str(uuid.uuid4())
    file_path = os.path.join(SHARED_DIR, f"{share_id}.json")

    share_content = {
        "share_id": share_id,
        "repo_url": repo_url,
        "repo_name": repo_name,
        "thread_title": thread_data.get("title", "未命名對話"),
        "messages": thread_data.get("messages", []),
        "created_at": str(os.path.getctime(HISTORY_FILE))  # 簡單用一下時間戳
    }

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(share_content, f, ensure_ascii=False, indent=2)
        return share_id
    except Exception as e:
        print(f"分享失敗: {e}")
        return None


def load_shared_chat(share_id):
    """
    讀取分享檔案
    """
    file_path = os.path.join(SHARED_DIR, f"{share_id}.json")
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None