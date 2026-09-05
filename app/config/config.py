import os

# Constantes globales (indépendantes de la source)
JSONL_EXT = "jsonl"

WEAVIATE_HOST = "localhost"
WEAVIATE_PORT = 9090
WEAVIATE_GRPC_PORT = 50051

RAW_DATA_DIR = "./data/raw"
CHUNKS_DATA_DIR = "./data/chunks"
RAW_SRC_DIR = "./data/raw_src"

STATUS_DIR = "./data/status"
RUNS_HISTORY = 10

USER_AGENT = os.getenv(
    "RAG_USER_AGENT",
    "personal-rag/1.0 (compatible; +https://github.com/vno99/personal_rag)",
)

CHUNK_TOKENIZER = "sentence-transformers/all-mpnet-base-v2"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 75
MAX_TOKEN_SIZE = 512

BATCH_SIZE_DOCS = 500
BATCH_SIZE_WEAVIATE = 100
EMBEDDING_MODEL_NAME = "sentence-transformers/all-mpnet-base-v2"
EMBEDDING_DEVICE = "cuda:0"
NORMALIZE_EMBEDDINGS = True

# Sources de documentation
SOURCES = [
    {
        "name": "snowflake",
        "type": "sitemap",
        "sitemap_url": "https://docs.snowflake.com/sitemap.xml",
        "filter_urls": [r"https://docs\.snowflake\.com/en/.*"],
        "collection": "SnowflakeDocs",
        "content_selector": "article",
    },
    {
        "name": "databricks",
        "type": "sitemap",
        "sitemap_url": "https://docs.databricks.com/en/doc-sitemap.xml",
        "filter_urls": [r"https://docs\.databricks\.com/aws/en/.*"],
        "collection": "DatabricksDocs",
        "content_selector": "article",
    },
    {
        "name": "nextjs",
        "type": "sitemap",
        "sitemap_url": "https://nextjs.org/sitemap.xml",
        "filter_urls": [r"https://nextjs\.org/docs/.*"],
        "collection": "NextJSDocs",
        "content_selector": "article",
    },
    {
        "name": "typescript",
        "type": "git",
        "repo_url": "https://github.com/microsoft/TypeScript-Website.git",
        "branch": "v2",
        "docs_path": "packages/documentation/copy/en",
        "collection": "TypeScriptDocs",
        "content_selector": None,
    },
    {
        "name": "python",
        "type": "archive",
        "archive_url": "https://docs.python.org/3.14/archives/python-3.14-docs-html.zip",
        "collection": "PythonDocs",
        "content_selector": "[role='main']",
    },
]


def get_source(name: str) -> dict:
    for source in SOURCES:
        if source["name"] == name:
            return source
    raise KeyError(f"Source inconnue: {name}")


def get_collection(name: str) -> str:
    return get_source(name)["collection"]


def docs_pattern(name: str) -> str:
    return f"{name}_docs_batch_"


def chunks_pattern(name: str) -> str:
    return f"{name}_chunks_batch_"
