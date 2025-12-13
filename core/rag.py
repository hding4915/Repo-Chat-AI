import os
import streamlit as st
from core.ingestion import get_repo_id
from core.config import VECTOR_STORE_DIR
from core.factory import get_embedding_model


@st.cache_resource(show_spinner=False)
def get_retriever(repo_url, embedding_config):
    # Lazy Import
    from langchain_community.vectorstores import Chroma

    repo_id = get_repo_id(repo_url)
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

    # --- 還原設定：k=20 ---
    # 抓取最相關的 20 個片段，這通常足夠包含 README 的核心內容，又不會有太多雜訊
    return db.as_retriever(
        search_type="mmr",
        search_kwargs={"k": 20, "fetch_k": 50}
    )


def get_qa_chain(repo_url, api_key, ollama_url, embedding_config=None):
    from langchain_mistralai import ChatMistralAI
    from langchain_classic.prompts import PromptTemplate
    from langchain_classic.chains import ConversationalRetrievalChain
    from langchain_classic.memory import ConversationSummaryMemory

    if embedding_config is None:
        embedding_config = {"provider": "Ollama", "model": "nomic-embed-text", "base_url": ollama_url}

    retriever = get_retriever(repo_url, embedding_config)
    if not retriever:
        return None

    llm = ChatMistralAI(
        api_key=api_key,
        model="codestral-latest",
        temperature=0,  # 溫度設為 0，讓回答最穩定、最不瞎掰
        streaming=True
    )

    memory = ConversationSummaryMemory(
        llm=llm,
        memory_key='chat_history',
        return_messages=True,
        output_key='answer'
    )

    # --- 還原設定：經典簡單 Prompt ---
    # 不要叫它扮演偵探，也不要給太複雜的規則，直接給它資料叫它回答
    custom_template = """Use the following pieces of context to answer the question at the end.
    If you don't know the answer, just say that you don't know, don't try to make up an answer.
    Answer in Traditional Chinese (繁體中文).

    {context}

    Chat History:
    {chat_history}

    Question: {question}

    Answer:"""

    QA_CHAIN_PROMPT = PromptTemplate(
        input_variables=["context", "chat_history", "question"],
        template=custom_template
    )

    qa_chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        memory=memory,
        combine_docs_chain_kwargs={"prompt": QA_CHAIN_PROMPT},
        return_source_documents=True  # 還是保留這個，方便你除錯看來源
    )

    return qa_chain