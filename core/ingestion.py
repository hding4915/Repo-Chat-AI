import os
import shutil
import hashlib
import re
import threading
import stat
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.config import SUPPORTED_EXTENSIONS, REPO_DOWNLOAD_DIR, VECTOR_STORE_DIR
from core.factory import get_embedding_model

try:
    from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
except ImportError:
    from streamlit.scriptrunner import add_script_run_ctx, get_script_run_ctx


def get_repo_id(repo_url):
    # 包含 #branch 在內的完整字串做 Hash，這樣不同分支會存成不同 ID
    return hashlib.md5(repo_url.strip().rstrip("/").encode()).hexdigest()


def clean_url(url):
    """
    淨化 URL，支援 HTTPS 和 SSH 格式。
    同時保留 #branch 資訊以便後續解析。
    """
    # 這裡的 Regex 會抓取直到空白為止的字串，包含 #
    match = re.search(r'((?:https?://|git@)[^\s]+)', url)
    if match: return match.group(1)
    return url.strip()


def force_remove_readonly(func, path, excinfo):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception as e:
        print(f"⚠️ 強制刪除失敗: {path}, 錯誤: {e}")


def remove_repo_data(repo_url):
    repo_id = get_repo_id(repo_url)
    repo_path = os.path.join(REPO_DOWNLOAD_DIR, repo_id)
    db_path = os.path.join(VECTOR_STORE_DIR, repo_id)
    deleted = False
    if os.path.exists(repo_path): shutil.rmtree(repo_path, onerror=force_remove_readonly); deleted = True
    if os.path.exists(db_path): shutil.rmtree(db_path, onerror=force_remove_readonly); deleted = True
    return deleted


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

    # 1. 處理 URL 與 Branch
    repo_url = clean_url(repo_url)

    # 解析 #branch 語法
    target_branch = None
    if "#" in repo_url:
        repo_url, target_branch = repo_url.rsplit("#", 1)
        print(f"📍 偵測到指定分支: {target_branch}")

    # 2. 計算 ID (使用包含分支的原始 URL 概念，但這裡為了方便重新組裝字串傳給 get_repo_id)
    # 注意：我們已經在外面傳進來的時候決定了 repo_url (含 #)，所以 get_repo_id 會算出唯一的 ID
    # 這裡我們需要用 "原始的完整輸入" 來算 ID，確保不同分支分開存
    full_url_for_id = f"{repo_url}#{target_branch}" if target_branch else repo_url
    repo_id = get_repo_id(full_url_for_id)

    repo_path = os.path.join(REPO_DOWNLOAD_DIR, repo_id)
    db_path = os.path.join(VECTOR_STORE_DIR, repo_id)
    hash_file = os.path.join(VECTOR_STORE_DIR, repo_id, "commit_hash.txt")

    def update_status(msg, progress):
        if progress_callback: progress_callback(msg, progress)

    # 0. 檢查 Hash (ls-remote 也支援分支)
    update_status("🔍 檢查版本...", 5)
    g = git.cmd.Git()
    try:
        g.config("--global", "http.postBuffer", "524288000")
        # 如果有指定分支，ls-remote 需要指定 ref
        ref = target_branch if target_branch else 'HEAD'
        latest_hash = g.ls_remote(repo_url, ref).split('\t')[0]
    except Exception:
        latest_hash = None

    if not force_update and os.path.exists(db_path) and os.path.exists(hash_file):
        with open(hash_file, "r") as f:
            local_hash = f.read().strip()
        if latest_hash and local_hash == latest_hash:
            update_status("⚡ 版本未變，載入快取", 100)
            return db_path, "skipped"

    if os.path.exists(repo_path): shutil.rmtree(repo_path, onerror=force_remove_readonly)
    if os.path.exists(db_path): shutil.rmtree(db_path, onerror=force_remove_readonly)

    # 1. Clone (支援分支參數)
    update_status(f"⬇️ 開始 Clone ({target_branch if target_branch else 'Default'})...", 10)
    try:
        clone_kwargs = {
            "depth": 1,
            "single_branch": True,
            "progress": CloneProgress()
        }
        if target_branch:
            clone_kwargs["branch"] = target_branch

        git.Repo.clone_from(repo_url, repo_path, **clone_kwargs)

    except Exception as e:
        error_msg = str(e)
        if "exit code(128)" in error_msg:
            if "not found" in error_msg.lower():
                raise Exception(f"找不到專案: {repo_url}")
            elif "permission denied" in error_msg.lower() or "publickey" in error_msg.lower():
                raise Exception(f"SSH 權限拒絕。請確認 SSH Key 設定。\n網址: {repo_url}")
            else:
                raise Exception(f"Git Clone 失敗: {error_msg}")
        raise Exception(f"Clone 失敗: {e}")

    update_status("📂 掃描檔案中...", 45)
    raw_documents = []
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

                    doc = Document(
                        page_content=content,
                        metadata={"source": rel_path, "repo": repo_url}  # 這裡 repo 只存 URL，不一定要存 branch
                    )
                    raw_documents.append(doc)
                    file_count += 1
                    if file_count >= MAX_FILES: break
                except:
                    pass
        if file_count % 200 == 0: update_status(f"📂 已讀取 {file_count} 個檔案...",
                                                45 + int(file_count / MAX_FILES * 15))

    if not raw_documents: raise Exception("No valid files found.")

    update_status(f"✂️ 切分與注入上下文...", 60)

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=150
    )

    split_docs = text_splitter.split_documents(raw_documents)

    final_docs = []
    for doc in split_docs:
        rel_path = doc.metadata.get("source", "unknown")
        doc.page_content = f"File: {rel_path}\nRepo: {repo_url}\n\n{doc.page_content}"
        final_docs.append(doc)

    total_chunks = len(final_docs)

    if not embedding_config:
        embedding_config = {"provider": "Ollama", "model": "nomic-embed-text", "base_url": "http://localhost:11434"}

    update_status(f"🧠 初始化向量計算 ({embedding_config['provider']})...", 65)

    embedding_model = get_embedding_model(
        provider=embedding_config['provider'],
        model_name=embedding_config['model'],
        api_key=embedding_config.get('api_key'),
        base_url=embedding_config.get('base_url')
    )

    if not embedding_model: raise Exception("Embedding 模型初始化失敗")

    db = Chroma(embedding_function=embedding_model, persist_directory=db_path)

    BATCH_SIZE = 64
    MAX_WORKERS = 12

    def compute_batch_embeddings(batch_docs):
        for attempt in range(3):
            try:
                b_texts = [d.page_content for d in batch_docs]
                b_embeddings = embedding_model.embed_documents(b_texts)
                return batch_docs, b_embeddings
            except Exception as e:
                if attempt == 2: raise e
                time.sleep(1 * (attempt + 1))

    total_processed = 0
    futures = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        update_status(f"🚀 全速運算中... (Chunks={total_chunks})", 68)

        for i in range(0, total_chunks, BATCH_SIZE):
            batch = final_docs[i: i + BATCH_SIZE]
            futures.append(executor.submit(compute_batch_embeddings, batch))

        completed_batches = 0
        for future in as_completed(futures):
            try:
                batch_docs, batch_embeddings = future.result()
                db.add_texts(texts=[d.page_content for d in batch_docs], metadatas=[d.metadata for d in batch_docs],
                             embeddings=batch_embeddings)

                total_processed += len(batch_docs)
                completed_batches += 1

                elapsed_time = time.time() - start_time
                if completed_batches > 0:
                    avg_time_per_batch = elapsed_time / completed_batches
                    remaining_batches = len(futures) - completed_batches
                    eta_seconds = int(remaining_batches * avg_time_per_batch)
                    if eta_seconds < 60:
                        eta_str = f"{eta_seconds}s"
                    else:
                        eta_str = f"{eta_seconds // 60}m {eta_seconds % 60}s"
                else:
                    eta_str = "計算中..."

                progress_percent = 70 + int((total_processed / total_chunks) * 29)
                msg = f"🧠 Embedding: {total_processed}/{total_chunks} ({int(total_processed / total_chunks * 100)}%) | 剩餘時間: {eta_str}"
                update_status(msg, progress_percent)
            except Exception as e:
                print(f"⚠️ Batch embedding 失敗: {e}")

    if latest_hash:
        os.makedirs(db_path, exist_ok=True)
        with open(hash_file, "w") as f: f.write(latest_hash)

    update_status("✅ Ready!", 100)
    return db_path, "updated"