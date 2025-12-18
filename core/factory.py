import streamlit as st


def get_embedding_model(provider, model_name, api_key=None, base_url=None):
    try:
        if provider == "Ollama":
            from langchain_community.embeddings import OllamaEmbeddings

            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            return OllamaEmbeddings(
                model=model_name,
                base_url=base_url,
                headers=headers
            )

        elif provider == "Mistral AI":
            from langchain_mistralai import MistralAIEmbeddings
            if not api_key:
                raise ValueError("使用 Mistral Embedding 需要 API Key")
            return MistralAIEmbeddings(
                model=model_name,
                api_key=api_key
            )

        elif provider == "OpenAI":
            from langchain_openai import OpenAIEmbeddings
            if not api_key:
                raise ValueError("使用 OpenAI Embedding 需要 API Key")
            return OpenAIEmbeddings(
                model=model_name,
                api_key=api_key
            )

        else:
            raise ValueError(f"不支援的 Embedding Provider: {provider}")

    except ImportError as e:
        st.error(f"缺少必要的套件: {e}")
        return None
    except Exception as e:
        st.error(f"初始化 Embedding 模型失敗: {e}")
        return None