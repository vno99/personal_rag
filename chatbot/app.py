import os
import re

import streamlit as st
import torch
import weaviate
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_mistralai import ChatMistralAI
from langdetect import detect
from weaviate.classes.query import HybridFusion, MetadataQuery
from deep_translator import GoogleTranslator

WEAVIATE_HOST = "host.docker.internal"
WEAVIATE_PORT = 9090
WEAVIATE_GRPC_PORT = 50051
COLLECTION_NAME = "DatabricksDocs"
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"

NORMALIZE_EMBEDDINGS = True
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

MIN_VECTOR_SCORE = 0.45
TOP_K = 3
ALPHA = 0.7
TEMPERATURE = 0.1
MAX_TOKEN = 1500
LLM_MODEL = "mistral-large-latest"

COLLECTIONS = [
    {
        "name": "SnowflakeDocs",
        "description": "Snowflake documentation : https://docs.snowflake.com"
    },
    {
        "name": "DatabricksDocs",
        "description": "Databricks documentation : https://docs.databricks.com/en"
    },
]
COL_NAME_LIST = [col["name"] for col in COLLECTIONS]

LANGUAGES = ["Anglais", "Allemand", "Français", "Néerlandais"]

FALLBACK_MESSAGES = {
    "Anglais": "I cannot answer this question with the available context. This application is limited to the indexed documentation.",
    "Allemand": "Ich kann diese Frage mit dem verfügbaren Kontext nicht beantworten. Diese Anwendung ist auf die indizierte Dokumentation beschränkt.",
    "Français": "Je ne peux pas répondre à cette question avec le contexte disponible. Cette application est limitée à la documentation indexée.",
    "Néerlandais": "Ik kan deze vraag niet beantwoorden met de beschikbare context. Deze applicatie is beperkt tot de geïndexeerde documentatie."
}


@st.cache_resource
def get_embeddings():
    """
    Initializes a HuggingFace embeddings object .
    
    Returns:
        HuggingFaceEmbeddings: A configured instance of HuggingFaceEmbeddings
            ready to generate embeddings for text inputs.
    """
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": DEVICE},
        encode_kwargs={"normalize_embeddings": NORMALIZE_EMBEDDINGS},
    )

embeddings = get_embeddings()

def connect_client():
    """
    Connects to a Weaviate instance.
    
    Returns:
        weaviate.Client: A client instance configured to connect to the specified
        Weaviate host, port, and gRPC port.
    """
    return weaviate.connect_to_local(
        host=WEAVIATE_HOST,
        port=WEAVIATE_PORT,
        grpc_port=WEAVIATE_GRPC_PORT
    )


def extract_scores(explain_score: str):
    """
    Extracts raw vector and keyword scores from the explain_score string.

    Args:
        explain_score (str): The explanation string containing the score details.

    Returns:
        A tuple containing (vector_score, keyword_score).
            Returns (None, None) if the input is empty or no matches are found.
    """
    if not explain_score:
        return None, None

    vector_match = re.search(
        r"Result Set vector,?\s*hybridVector.*?original score ([0-9.]+)",
        explain_score,
        flags=re.IGNORECASE | re.DOTALL,
    )
    keyword_match = re.search(
        r"Result Set keyword,?\s*bm25.*?original score ([0-9.]+)",
        explain_score,
        flags=re.IGNORECASE | re.DOTALL,
    )

    vector_score = float(vector_match.group(1)) if vector_match else None
    keyword_score = float(keyword_match.group(1)) if keyword_match else None

    return vector_score, keyword_score


def is_english(text):
    """Checks if the provided text is in English.

    Args:
        text (str): The text to evaluate.

    Returns:
        bool: True if the detected language is English, False otherwise.
    """
    return detect(text) == 'en'


@st.cache_data(ttl=3600)
def translate_to_english(text):
    """Translates the input text to English using Google Translate.

    Args:
        text (str): The text to be translated.

    Returns:
        str: The translated text in English.
    """
    return GoogleTranslator(source='auto', target='en').translate(text)


def retrieve_context(query_text, top_k=TOP_K, collection_name=COLLECTION_NAME):
    """
    Performs hybrid retrieval with automatic translation to English.

    Args:
        query_text (str): The input query.
        top_k (int, optional): Number of documents to retrieve.
            Defaults to TOP_K.
        collection_name (str, optional): Target collection name.
            Defaults to COLLECTION_NAME.

    Returns:
        dict: A dictionary containing 'in_scope' (bool), 'reason' (str), 
              'context' (str), 'sources' (list), and 'debug' (list).
    """
    # Prepare the query: Translate if necessary in english and generate embedding
    query_text_en = translate_to_english(query_text) if not is_english(query_text) else query_text
    
    query_vector = embeddings.embed_query(query_text_en)
    client = connect_client()

    try:
        collection = client.collections.get(collection_name)
        
        # Execute the query
        response = collection.query.hybrid(
            query=query_text_en,
            vector=query_vector,
            alpha=ALPHA,
            limit=top_k,
            return_metadata=MetadataQuery(score=True, explain_score=True),
            fusion_type=HybridFusion.RELATIVE_SCORE,
        )
        
        # Parse results into a structured format
        results = []
        for obj in response.objects:
            props = obj.properties or {}
            explain_score = obj.metadata.explain_score or ""
            vector_score, keyword_score = extract_scores(explain_score)

            results.append({
                "content": props.get("content", ""),
                "source": props.get("source", "N/A"),
                "hybrid_score": float(obj.metadata.score) if obj.metadata.score is not None else 0.0,
                "vector_score": vector_score,
                "keyword_score": keyword_score,
                "explain_score": explain_score,
            })

        # Determine in_scope and reason based on results
        context = ""
        sources = []
        if not results:
            in_scope = False
            reason = "no_results"
            top1_vector_score = None
        else:
            in_scope = False
            top1 = results[0]
            top1_vector_score = top1["vector_score"]
            
            if top1_vector_score is None:
                reason = "missing_vector_score"
            elif top1_vector_score < MIN_VECTOR_SCORE:
                reason = f"vector_score_too_low ({top1_vector_score:.4f} < {MIN_VECTOR_SCORE})"
            else:
                in_scope = True
                reason = "ok"
                context = "\n\n".join([r["content"] for r in results if r["content"]])
                sources = [r["source"] for r in results]

        return {
            "in_scope": in_scope,
            "reason": reason,
            "context": context,
            "sources": sources,
            "debug": results if results else [],
        }

    finally:
        client.close()


def main():
    st.set_page_config(
        page_title="Personal RAG", 
        page_icon="",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    

    st.title("Personal RAG")
    st.markdown("**Interrogation de la doc indexée**")


    with st.sidebar:
        with st.container(border=True):
            st.header("Configuration")

            selected_collection = st.pills(
                "Sélectionnez la collection", 
                COL_NAME_LIST, 
                default=COLLECTION_NAME,
                required=True,
                selection_mode="single"
            )

            top_num = st.slider(
                "Top sources", 
                min_value=1, 
                max_value=10,
                value=TOP_K
            )

            selected_language = st.selectbox(
                "Langue de la réponse",
                LANGUAGES,
                index=2 # Français
            )

        if st.button("Tout effacer"):
            st.session_state.messages = []
            st.rerun()


    # Chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat messages from history on app rerun
    for i, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            # Show sources if available
            if "sources" in message and message["sources"]:
                with st.expander("📚 Sources"):
                    for i, src in enumerate(message["sources"]):
                        st.markdown(f"**#{i+1}** [{src}]({src})")

    # Accept user input
    if prompt := st.chat_input("Pose ta question ...", key="chat_input"):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Display assistant response in chat message container
        with st.chat_message("assistant"):
            with st.spinner("🔍 Retrieval + MistralAI..."):
                try:
                    # 1. Retrieval
                    result = retrieve_context(
                        prompt,
                        top_k=top_num,
                        collection_name=selected_collection
                    )

                    if not result["in_scope"]:
                        fallback = FALLBACK_MESSAGES[selected_language]
                        st.markdown(fallback)
                    else:
                        context = result["context"]
                    
                        llm = ChatMistralAI(
                            model=LLM_MODEL,
                            api_key=MISTRAL_API_KEY,
                            temperature=TEMPERATURE,
                            max_tokens=MAX_TOKEN,
                        )

                        rag_prompt = f"""<|role|>EXPERT<|end|>

                        AVAILABLE CONTEXT:
                        {context}

                        QUESTION: {prompt}

                        <|instructions|>
                        1. Provide a concise and complete answer. 
                           Stick strictly to the provided context. 
                           If the information is dense, use bullet points to maintain clarity CONTEXT.
                        2. If the information is not present in the context, reply only with: "Not in the provided documentation."
                           Do not add any other information.
                        3. For SQL/Python code, provide an exact copy from the context.
                        4. Language: {selected_language} (technical tone).
                        <|end|>

                        ANSWER:"""

                        response = llm.invoke(rag_prompt)
                        full_response = response.content

                        # Add assistant response to chat history
                        message = {
                            "role": "assistant", 
                            "content": full_response,
                            "sources": result["sources"]
                        }
                        st.session_state.messages.append(message)

                        # Show the response
                        st.markdown(full_response)

                        # Show sources if available
                        if "sources" in message and message["sources"]:
                            with st.expander("📚 Sources"):
                                for i, src in enumerate(message["sources"]):
                                    st.markdown(f"**#{i+1}** [{src}]({src})")

                except Exception as e:
                    full_response = f"Erreur: {str(e)}"
                

    st.markdown("---")
    st.markdown("")


if __name__ == "__main__":
    main()