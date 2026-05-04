
# SITEMAP_URL = "https://docs.databricks.com/en/doc-sitemap.xml"
# FILTER_URLS=[r"https://docs\.databricks\.com/aws/en/.*"]

# DOCS_FILE_PATTERN = "databricks_docs_batch_"
# CHUNKS_FILE_PATTERN = "databricks_chunks_batch_"

# COLLECTION_NAME = "DatabricksDocs"

SITEMAP_URL = "https://docs.snowflake.com/sitemap.xml"
FILTER_URLS=[r"https://docs\.snowflake\.com/en/.*"]

DOCS_FILE_PATTERN = "snowflake_docs_batch_"
CHUNKS_FILE_PATTERN = "snowflake_chunks_batch_"
JSONL_EXT = "jsonl"

WEAVIATE_HOST = "localhost"
WEAVIATE_PORT = 9090
WEAVIATE_GRPC_PORT = 50051
COLLECTION_NAME = "SnowflakeDocs"

RAW_DATA_DIR = "./data/raw"
CHUNKS_DATA_DIR = "./data/chunks"

CHUNK_TOKENIZER = "sentence-transformers/all-mpnet-base-v2"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 75
MAX_TOKEN_SIZE = 512

BATCH_SIZE_DOCS = 500
BATCH_SIZE_WEAVIATE = 100
EMBEDDING_MODEL_NAME = "sentence-transformers/all-mpnet-base-v2"

EMBEDDING_DEVICE = "cuda:0"
NORMALIZE_EMBEDDINGS = True
