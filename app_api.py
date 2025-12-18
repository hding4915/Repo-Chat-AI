import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from core.ingestion import ingest_repo, get_repo_id
from core.factory import get_embedding_model
from core.config import VECTOR_STORE_DIR

from langchain_community.vectorstores import Chroma
from langchain_mistralai import ChatMistralAI
from langchain_classic.prompts import PromptTemplate
from langchain_classic.chains import ConversationalRetrievalChain
from langchain_classic.memory import ConversationSummaryMemory


load_dotenv()

app = Flask(__name__)
CORS(app)


RETRIEVER_CACHE = {}



def get_api_embedding_config(data):
    return {
        "provider": data.get("emb_provider", "Ollama"),
        "model": data.get("emb_model", "nomic-embed-text"),
        "api_key": data.get("emb_api_key", os.getenv("OLLAMA_EMBEDDING_API_KEY", "")),
        "base_url": data.get("emb_base_url", os.getenv("OLLAMA_EMBEDDING_URL", "http://localhost:11434"))
    }


def get_retriever_for_api(repo_url, embedding_config):
    repo_id = get_repo_id(repo_url)

    if repo_id in RETRIEVER_CACHE:
        return RETRIEVER_CACHE[repo_id]

    db_path = os.path.join(VECTOR_STORE_DIR, repo_id)
    if not os.path.exists(db_path):
        return None

    embedding_model = get_embedding_model(
        provider=embedding_config['provider'],
        model_name=embedding_config['model'],
        api_key=embedding_config.get('api_key'),
        base_url=embedding_config.get('base_url')
    )

    if not embedding_model:
        return None

    db = Chroma(persist_directory=db_path, embedding_function=embedding_model)
    retriever = db.as_retriever(
        search_type="mmr",
        search_kwargs={"k": 50, "fetch_k": 200, "lambda_mult": 0.5}
    )

    RETRIEVER_CACHE[repo_id] = retriever
    return retriever


# --- API Endpoints ---

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "service": "Repo Chat API"})


@app.route('/api/ingest', methods=['POST'])
def api_ingest():
    data = request.json
    repo_url = data.get('repo_url')
    force_update = data.get('force_update', False)

    if not repo_url:
        return jsonify({"error": "Missing repo_url"}), 400

    embedding_config = get_api_embedding_config(data)

    def console_progress(msg, percent):
        print(f"[Ingest] {percent}% - {msg}")

    try:
        print(f"🚀 開始處理: {repo_url}")
        db_path, status = ingest_repo(
            repo_url=repo_url,
            progress_callback=console_progress,
            force_update=force_update,
            embedding_config=embedding_config
        )

        repo_id = get_repo_id(repo_url)
        if repo_id in RETRIEVER_CACHE:
            del RETRIEVER_CACHE[repo_id]

        return jsonify({
            "status": "success",
            "message": f"Repo processed successfully ({status})",
            "repo_id": repo_id,
            "db_path": db_path
        })

    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.json
    repo_url = data.get('repo_url')
    question = data.get('question')

    llm_api_key = data.get('api_key', os.getenv("MISTRAL_API_KEY", ""))

    if not repo_url or not question:
        return jsonify({"error": "Missing repo_url or question"}), 400

    embedding_config = get_api_embedding_config(data)
    retriever = get_retriever_for_api(repo_url, embedding_config)

    if not retriever:
        return jsonify({"error": "Repo not found. Please ingest it first."}), 404

    try:
        llm = ChatMistralAI(
            api_key=llm_api_key,
            model_name="codestral-latest",
            temperature=0.1
        )
    except Exception as e:
        return jsonify({"error": f"LLM Init failed: {str(e)}"}), 500

    memory = ConversationSummaryMemory(
        llm=llm,
        memory_key='chat_history',
        return_messages=True,
        output_key='answer'
    )

    client_history = data.get('chat_history', [])
    for msg in client_history:
        if msg['role'] == 'user':
            memory.chat_memory.add_user_message(msg['content'])
        elif msg['role'] == 'assistant':
            memory.chat_memory.add_ai_message(msg['content'])

    custom_template = """
    You are an expert software architect.
    Context:
    {context}

    Chat History:
    {chat_history}

    Question: {question}

    Answer (in Traditional Chinese):"""

    QA_CHAIN_PROMPT = PromptTemplate(input_variables=["context", "chat_history", "question"], template=custom_template)

    qa_chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        memory=memory,
        combine_docs_chain_kwargs={"prompt": QA_CHAIN_PROMPT},
        return_source_documents=True
    )

    try:
        result = qa_chain.invoke({"question": question})

        sources = []
        if "source_documents" in result:
            sources = list(set([doc.metadata.get("source", "Unknown") for doc in result["source_documents"]]))

        return jsonify({
            "answer": result["answer"],
            "sources": sources
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print("🚀 Repo Chat API Server running on port 5000")
    app.run(host='0.0.0.0', port=5000, debug=True)