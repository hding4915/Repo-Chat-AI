import os
import streamlit as st
from core.ingestion import get_repo_id
from core.config import VECTOR_STORE_DIR
from core.factory import get_embedding_model  # 引入工廠


@st.cache_resource(show_spinner=False)
def get_retriever(repo_url, embedding_config):
    # Lazy Import
    from langchain_community.vectorstores import Chroma

    repo_id = get_repo_id(repo_url)
    db_path = os.path.join(VECTOR_STORE_DIR, repo_id)

    if not os.path.exists(db_path):
        return None

        # --- 使用工廠還原 Embedding Model ---
    embedding_model = get_embedding_model(
        provider=embedding_config['provider'],
        model_name=embedding_config['model'],
        api_key=embedding_config.get('api_key'),
        base_url=embedding_config.get('base_url')
    )

    if not embedding_model:
        return None

    db = Chroma(persist_directory=db_path, embedding_function=embedding_model)

    return db.as_retriever(
        search_type="mmr",
        search_kwargs={"k": 30, "fetch_k": 100, "lambda_mult": 0.5}
    )


def get_qa_chain(repo_url, api_key, ollama_url, embedding_config):
    # Lazy Import
    from langchain_mistralai import ChatMistralAI
    from langchain_classic.prompts import PromptTemplate
    from langchain_classic.chains import ConversationalRetrievalChain
    from langchain_classic.memory import ConversationSummaryMemory

    # 傳入 embedding_config 字典
    retriever = get_retriever(repo_url, embedding_config)
    if not retriever:
        return None

    # LLM (Chat Model)
    # 這裡我們假設 Chat Model 還是先用 Mistral (之後你可以再把 Chat Model 也改成工廠模式)
    # 為了保持變動最小，這裡先不動 Chat 的邏輯
    llm = ChatMistralAI(
        api_key=api_key,
        model_name="codestral-latest",
        temperature=0.1,
        streaming=True
    )

    memory = ConversationSummaryMemory(llm=llm, memory_key='chat_history', return_messages=True)

    custom_template = """
    You are a senior software architect and code analysis assistant.
    You have access to a set of code snippets retrieved from a GitHub repository.
    Each code snippet starts with "File: <path>".

    Your Goal: Answer the user's question accurately based ONLY on the provided context.

    Guidelines:
    1. **Project Overview**: If the user asks "what does this project do?", look for 'README.md', 'main.py', 'app.py', or 'index.js'.
    2. **Inference**: If 'README.md' is missing, infer the project's purpose by analyzing file structure and imports.
    3. **Transparency**: If context is insufficient, admit it.
    4. **Language**: Always answer in the same language as the user's question.

    Context from the repository:
    --------------------------------
    {context}
    --------------------------------

    Chat History:
    {chat_history}

    User Question: {question}

    Your Professional Answer:"""

    QA_CHAIN_PROMPT = PromptTemplate(
        input_variables=["context", "chat_history", "question"],
        template=custom_template
    )

    qa_chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        memory=memory,
        combine_docs_chain_kwargs={"prompt": QA_CHAIN_PROMPT}
    )

    return qa_chain