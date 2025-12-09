import os
import shutil
import hashlib
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.config import SUPPORTED_EXTENSIONS, REPO_DOWNLOAD_DIR, VECTOR_STORE_DIR
from core.factory import get_embedding_model  # 引入工廠

try:
    from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
except ImportError:
    from streamlit.scriptrunner import add_script_run_ctx, get_script_run_ctx


def get_repo_id(repo_url):
    return hashlib.md5(repo_url.strip().rstrip("/").encode()).hexdigest()


def clean_url(url):
    match = re.search(r'(https?://[^\s]+)', url)
    if match: return match.group(1)
    return url.strip()


def remove_repo_data(repo_url):
    repo_id = get_repo_id(repo_url)
    repo_path = os.path.join(REPO_DOWNLOAD_DIR, repo_id)
    db_path = os.path.join(VECTOR_STORE_DIR, repo_id)
    deleted = False
    if os.path.exists(repo_path): shutil.rmtree(repo_path, ignore_errors=True); deleted = True
    if os.path.exists(db_path): shutil.rmtree(db_path, ignore_errors=True); deleted = True
    return deleted


# --- 關鍵修改：接收 embedding_config 字典 ---
def ingest_repo(repo_url, progress_callback=None, force_update=False, embedding_config=None):
    import git
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import Chroma
    from langchain_core.documents import Document

    try:
        main_thread_ctx = get_script_run_ctx()
    except Exception:
        main_thread_ctx = None

    class CloneProgress(git.RemoteProgress):
        def update(self, op_code, cur_count, max_count=None, message=''):
            if main_thread_ctx: add_script_run_ctx(threading.current_thread(), main_thread_ctx)
            operation = "Cloning"
            if op_code & git.RemoteProgress.COUNTING:
                operation = "Counting"
            elif op_code & git.RemoteProgress.COMPRESSING:
                operation = "Compressing"
            elif op_code & git.RemoteProgress.RECEIVING:
                operation = "Receiving"
            elif op_code & git.RemoteProgress.RESOLVING:
                operation = "Resolving"
            if max_count:
                percent = int(cur_count / max_count * 100)
                ui_progress = 10 + int(percent * 0.3)
                msg = f"⬇️ {operation}: {percent}% ({cur_count}/{max_count})"
            else:
                ui_progress = 10
                msg = f"⬇️ {operation}: {cur_count} objects..."
            if progress_callback: progress_callback(msg, ui_progress)

    original_url = repo_url
    repo_url = clean_url(repo_url)
    if original_url != repo_url: print(f"⚠️ 網址修正: {repo_url}")

    repo_id = get_repo_id(repo_url)
    repo_path = os.path.join(REPO_DOWNLOAD_DIR, repo_id)
    db_path = os.path.join(VECTOR_STORE_DIR, repo_id)
    hash_file = os.path.join(VECTOR_STORE_DIR, repo_id, "commit_hash.txt")

    def update_status(msg, progress):
        if progress_callback: progress_callback(msg, progress)

    update_status("🔍 檢查版本...", 5)
    g = git.cmd.Git()
    try:
        g.config("--global", "http.postBuffer", "524288000")
        latest_hash = g.ls_remote(repo_url, 'HEAD').split('\t')[0]
    except Exception:
        latest_hash = None

    if not force_update and os.path.exists(db_path) and os.path.exists(hash_file):
        with open(hash_file, "r") as f:
            local_hash = f.read().strip()
        if latest_hash and local_hash == latest_hash:
            update_status("⚡ 版本未變，載入快取", 100)
            return db_path, "skipped"

    if os.path.exists(repo_path): shutil.rmtree(repo_path, ignore_errors=True)
    if os.path.exists(db_path): shutil.rmtree(db_path)

    update_status(f"⬇️ 開始 Clone (深度 1)...", 10)
    try:
        git.Repo.clone_from(repo_url, repo_path, depth=1, single_branch=True, progress=CloneProgress())
    except Exception as e:
        error_msg = str(e)
        if "exit code(128)" in error_msg:
            if "not found" in error_msg.lower():
                raise Exception(f"找不到專案: {repo_url}")
            else:
                raise Exception(f"Git Clone 失敗: {error_msg}")
        raise Exception(f"Clone 失敗: {e}")

    update_status("📂 掃描檔案中...", 45)
    documents = []
    MAX_FILES = 5000
    file_count = 0
    for root, dirs, files in os.walk(repo_path):
        if file_count >= MAX_FILES: break
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, repo_path)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    if not content.strip(): continue
                    content_with_context = f"File: {rel_path}\nRepo: {repo_url}\n\n{content}"
                    doc = Document(page_content=content_with_context, metadata={"source": rel_path, "repo": repo_url})
                    documents.append(doc)
                    file_count += 1
                    if file_count >= MAX_FILES: break
                except:
                    pass
        if file_count % 200 == 0: update_status(f"📂 已讀取 {file_count} 個檔案...",
                                                45 + int(file_count / MAX_FILES * 15))

    if not documents: raise Exception("No valid files found.")

    update_status(f"✂️ 切分與整理...", 60)
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
    texts = text_splitter.split_documents(documents)
    total_chunks = len(texts)

    # --- 使用工廠建立 Embedding Model ---
    if not embedding_config:
        # Default fallback
        embedding_config = {"provider": "Ollama", "model": "nomic-embed-text", "base_url": "http://localhost:11434"}

    update_status(f"🧠 初始化向量計算 ({embedding_config['provider']}: {embedding_config['model']})...", 65)

    embedding_model = get_embedding_model(
        provider=embedding_config['provider'],
        model_name=embedding_config['model'],
        api_key=embedding_config.get('api_key'),
        base_url=embedding_config.get('base_url')
    )

    if not embedding_model:
        raise Exception("Embedding 模型初始化失敗，請檢查設定")

    db = Chroma(embedding_function=embedding_model, persist_directory=db_path)
    BATCH_SIZE = 500
    MAX_WORKERS = 4

    def compute_batch_embeddings(batch_docs):
        b_texts = [d.page_content for d in batch_docs]
        b_embeddings = embedding_model.embed_documents(b_texts)
        return batch_docs, b_embeddings

    total_processed = 0
    futures = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for i in range(0, total_chunks, BATCH_SIZE):
            batch = texts[i: i + BATCH_SIZE]
            futures.append(executor.submit(compute_batch_embeddings, batch))

        for future in as_completed(futures):
            try:
                batch_docs, batch_embeddings = future.result()
                db.add_texts(texts=[d.page_content for d in batch_docs], metadatas=[d.metadata for d in batch_docs],
                             embeddings=batch_embeddings)
                total_processed += len(batch_docs)
                progress_percent = 70 + int((total_processed / total_chunks) * 29)
                update_status(f"🧠 Embedding: {total_processed}/{total_chunks}", progress_percent)
            except Exception as e:
                print(f"⚠️ Batch embedding 失敗: {e}")

    if latest_hash:
        os.makedirs(db_path, exist_ok=True)
        with open(hash_file, "w") as f: f.write(latest_hash)

    update_status("✅ Ready!", 100)
    return db_path, "updated"