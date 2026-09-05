import os

import streamlit as st
import torch
import weaviate
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_mistralai import ChatMistralAI
from langdetect import detect
from weaviate.classes.query import HybridFusion, MetadataQuery
from deep_translator import GoogleTranslator

from extract_scores import extract_scores
from fusion import fuse, is_in_scope

WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "host.docker.internal")
WEAVIATE_PORT = int(os.getenv("WEAVIATE_PORT", "9090"))
WEAVIATE_GRPC_PORT = int(os.getenv("WEAVIATE_GRPC_PORT", "50051"))
COLLECTION_NAME = "DatabricksDocs"
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
# Sentinelle du `.env_example` : si l'utilisateur a copié le template sans
# remplacer la valeur, on l'alerte plutôt que de le laisser échouer à la
# première question (cf. code review E).
_MISTRAL_SENTINEL = "aaaaaaaaaaaaaaaaaaa"

EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"

NORMALIZE_EMBEDDINGS = True
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

MIN_VECTOR_SCORE = 0.45
TOP_K = 3
ALPHA = 0.7
TEMPERATURE = 0.1
MAX_TOKEN = 1500
LLM_MODEL = os.getenv("MISTRAL_MODEL", "mistral-medium-latest")

COLLECTIONS = [
    {
        "name": "SnowflakeDocs",
        "description": "Snowflake documentation : https://docs.snowflake.com"
    },
    {
        "name": "DatabricksDocs",
        "description": "Databricks documentation : https://docs.databricks.com/en"
    },
    {
        "name": "NextJSDocs",
        "description": "Next.js documentation : https://nextjs.org/docs"
    },
    {
        "name": "TypeScriptDocs",
        "description": "TypeScript documentation : https://www.typescriptlang.org/docs"
    },
    {
        "name": "PythonDocs",
        "description": "Python documentation : https://docs.python.org/3"
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


def query_one_collection(client, collection_name, query_text_en, query_vector, top_k):
    """Exécute une recherche hybride sur une collection et parse les résultats."""
    collection = client.collections.get(collection_name)

    response = collection.query.hybrid(
        query=query_text_en,
        vector=query_vector,
        alpha=ALPHA,
        limit=top_k,
        return_metadata=MetadataQuery(score=True, explain_score=True),
        fusion_type=HybridFusion.RELATIVE_SCORE,
    )

    results = []
    for obj in response.objects:
        props = obj.properties or {}
        explain_score = obj.metadata.explain_score or ""
        vector_score, keyword_score = extract_scores(explain_score)

        results.append({
            "collection": collection_name,
            "content": props.get("content", ""),
            "source": props.get("source", "N/A"),
            "hybrid_score": float(obj.metadata.score) if obj.metadata.score is not None else 0.0,
            "vector_score": vector_score,
            "keyword_score": keyword_score,
            "explain_score": explain_score,
        })

    return results


def retrieve_context(query_text, top_k=TOP_K, collections=None):
    """
    Recherche hybride multi-collections avec fusion min-max par collection.

    Args:
        query_text (str): La requête (auto-traduite en anglais si besoin).
        top_k (int, optional): Nombre de résultats à garder après fusion.
            Defaults to TOP_K.
        collections (list[str], optional): Noms des collections à interroger.
            Defaults to [COLLECTION_NAME].

    Returns:
        dict: 'in_scope' (bool), 'reason' (str), 'context' (str),
              'sources' (list), 'debug' (list, résultats fusionnés).
    """
    if collections is None:
        collections = [COLLECTION_NAME]

    query_text_en = translate_to_english(query_text) if not is_english(query_text) else query_text
    query_vector = embeddings.embed_query(query_text_en)
    client = connect_client()

    try:
        # Ignore les collections configurées mais non encore ingérées en base
        existing = [name for name in collections if client.collections.exists(name)]
        if not existing:
            return {
                "in_scope": False,
                "reason": "no_results",
                "context": "",
                "sources": [],
                "debug": [],
            }

        results_by_collection = [
            query_one_collection(client, name, query_text_en, query_vector, top_k)
            for name in existing
        ]

        fused = fuse(results_by_collection, top_k=top_k)

        if not fused:
            return {
                "in_scope": False,
                "reason": "no_results",
                "context": "",
                "sources": [],
                "debug": [],
            }

        if not is_in_scope(fused, min_vector_score=MIN_VECTOR_SCORE):
            top1 = fused[0]["vector_score"]
            return {
                "in_scope": False,
                "reason": f"vector_score_too_low ({top1} < {MIN_VECTOR_SCORE})",
                "context": "",
                "sources": [],
                "debug": fused,
            }

        context = "\n\n".join([r["content"] for r in fused if r.get("content")])
        sources = [r["source"] for r in fused]

        return {
            "in_scope": True,
            "reason": "ok",
            "context": context,
            "sources": sources,
            "debug": fused,
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

            selected_collections = st.multiselect(
                "Collections à interroger",
                COL_NAME_LIST,
                default=COL_NAME_LIST,
                help="Sélectionnez une ou plusieurs collections. Par défaut : toutes.",
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

        if not MISTRAL_API_KEY or MISTRAL_API_KEY == _MISTRAL_SENTINEL:
            st.warning(
                "⚠️ `MISTRAL_API_KEY` non définie (ou valeur sentinelle du "
                "`.env_example`). Copie `.env_example` vers `.env` et "
                "remplace la valeur. Les réponses LLM échoueront sinon.",
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
                        collections=selected_collections,
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
                    full_response = f"⚠️ Erreur : {e}"
                    st.session_state.messages.append({"role": "assistant", "content": full_response})
                    st.error(full_response)
                

    st.markdown("---")
    st.markdown("")


if __name__ == "__main__":
    main()