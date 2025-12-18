import os
from pathlib import Path

HOME_DIR = str(Path.home())
BASE_DATA_DIR = os.path.join(HOME_DIR, "repo-chat-data")

VECTOR_STORE_DIR = os.path.join(BASE_DATA_DIR, "vector_stores")
REPO_DOWNLOAD_DIR = os.path.join(BASE_DATA_DIR, "repos")
HISTORY_FILE = os.path.join(BASE_DATA_DIR, "history.json")
MISTRAL_API_KEY = "GkFTyXYWJuJbZkU46nm7hd7LTRPSm1Ee"


SHARED_DIR = os.path.join(BASE_DATA_DIR, "shared_chats")

SUPPORTED_EXTENSIONS = {
    ".py", ".ipynb", ".js", ".jsx", ".ts", ".tsx",
    ".c", ".cpp", ".h", ".hpp", ".java", ".kt",
    ".go", ".rs", ".php", ".rb", ".cs",
    ".md", ".txt", ".rst",
    ".json", ".yaml", ".yml", ".toml", ".xml", ".gradle"
}

os.makedirs(VECTOR_STORE_DIR, exist_ok=True)
os.makedirs(REPO_DOWNLOAD_DIR, exist_ok=True)
os.makedirs(SHARED_DIR, exist_ok=True)

print(f"📂 資料儲存路徑: {BASE_DATA_DIR}")