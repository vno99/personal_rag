import json
import uuid
from pathlib import Path

import config.config as config
import torch
import weaviate
from config.logger_config import setup_logging
from langchain_huggingface import HuggingFaceEmbeddings
from weaviate.classes.config import Configure, DataType, Property
from weaviate.classes.data import DataObject

logger = setup_logging(__name__)

CHUNKS_FILE_PATTERN = config.CHUNKS_FILE_PATTERN
JSONL_EXT = config.JSONL_EXT

CHUNKS_DATA_DIR = Path(config.CHUNKS_DATA_DIR)
COLLECTION_NAME = config.COLLECTION_NAME

WEAVIATE_HOST = config.WEAVIATE_HOST
WEAVIATE_PORT = config.WEAVIATE_PORT
WEAVIATE_GRPC_PORT = config.WEAVIATE_GRPC_PORT

BATCH_SIZE_WEAVIATE = config.BATCH_SIZE_WEAVIATE
EMBEDDING_MODEL_NAME = config.EMBEDDING_MODEL_NAME

EMBEDDING_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
NORMALIZE_EMBEDDINGS = config.NORMALIZE_EMBEDDINGS


def get_embeddings():
    """
    Initializes a HuggingFace embeddings object .
    
    Returns:
        HuggingFaceEmbeddings: A configured instance of HuggingFaceEmbeddings
            ready to generate embeddings for text inputs.
    """
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_NAME,
        model_kwargs={"device": EMBEDDING_DEVICE},
        encode_kwargs={"normalize_embeddings": NORMALIZE_EMBEDDINGS},
    )


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
        grpc_port=WEAVIATE_GRPC_PORT,
    )


def get_collection(client):
    """
    Ensure the Weaviate collection exists, creating it if necessary.
    
    Parameters:
    -----------
    client : WeaviateClient
        The Weaviate client instance to interact with the database
        
    Returns:
    --------
    Collection
        The existing or newly created collection
    """
    existing_coll = client.collections.list_all()

    if COLLECTION_NAME in existing_coll:
        logger.info(f"Collection '{COLLECTION_NAME}' existe déjà")
        return client.collections.get(COLLECTION_NAME)

    logger.info(f"Création de la collection '{COLLECTION_NAME}'...")

    client.collections.create(
        name=COLLECTION_NAME,
        properties=[
            Property(name="chunk_id", data_type=DataType.TEXT),
            Property(name="source", data_type=DataType.TEXT),
            Property(name="loc", data_type=DataType.TEXT),
            Property(name="lastmod", data_type=DataType.TEXT),
            Property(name="chunk_index", data_type=DataType.INT),
            Property(name="chunk_size", data_type=DataType.INT),
            Property(name="content", data_type=DataType.TEXT),
        ],
        vector_config=Configure.Vectors.self_provided(),
    )

    logger.info(f"Collection '{COLLECTION_NAME}' créée")

    return client.collections.get(COLLECTION_NAME)


def read_jsonl_file(file_path: Path):
    """
    Generator function that reads a JSONL file and yields JSON objects line by line.
    
    Args:
        file_path (Path): Path to the JSONL file to read.
        
    Yields:
        dict: Parsed JSON object from each line of the file.
    """
    with file_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                logger.error(f"JSON invalide dans {file_path.name}, ligne {line_num}: {e}")


def batch_iterable(records, batch_size: int):
    """
    Generator function that yields batches of records.

    Args:
        records (Iterable): An iterable (list, generator, etc.) containing records.
        batch_size (int): The maximum number of records per batch.

    Yields:
        List: Each list contains up to `batch_size` records.
    """
    batch = []
    for item in records:
        batch.append(item)
        if len(batch) >= batch_size:
            yield batch
            batch = []

    if batch:
        yield batch


def ingest_file(weaviate_collection, embeddings, file_path: Path):
    """
    Reads a JSONL file, processes its records, and inserts them into a Weaviate collection.

    Args:
        weaviate_collection (DataCollection): The Weaviate collection to insert data into.
        embeddings (Embeddings): The embedding model to generate vectors from text content.
        file_path (Path): The path to the JSONL file containing records to ingest.
    """
    logger.info(f"Ingestion de {file_path.name}...")

    total = 0
    failed = 0

    records = read_jsonl_file(file_path)

    for batch_num, records_batch in enumerate(batch_iterable(records, BATCH_SIZE_WEAVIATE), start=1):
        texts = [record.get("content", "") for record in records_batch]

        try:
            # Generate embeddings for all texts in the batch
            vectors = embeddings.embed_documents(texts)
        except Exception as e:
            failed += len(records_batch)
            logger.error(f"Erreur embedding batch {batch_num} dans {file_path.name}: {e}")

            continue

        objects_to_insert = []

        # Process each record with its corresponding embedding vector
        for record, vector in zip(records_batch, vectors):
            chunk_id = record.get("chunk_id")
            if not chunk_id:
                failed += 1
                logger.info(f"chunk_id manquant dans {file_path.name}")
                continue
            
            # Create a DataObject for Weaviate
            obj = DataObject(
                uuid=str(uuid.uuid3(uuid.NAMESPACE_DNS, chunk_id)),
                properties={
                    "chunk_id": chunk_id,
                    "source": record.get("source"),
                    "loc": record.get("loc"),
                    "lastmod": record.get("lastmod"),
                    "chunk_index": record.get("chunk_index"),
                    "chunk_size": record.get("chunk_size"),
                    "content": record.get("content"),
                },
                vector=vector
            )

            objects_to_insert.append(obj)

        if not objects_to_insert:
            continue

        try:
            # Insert all objects in the batch into Weaviate
            response = weaviate_collection.data.insert_many(objects_to_insert)
            total += len(objects_to_insert)

            logger.info(f"batch {batch_num} : {len(objects_to_insert)} chunks insérés")

            # Check for errors returned by Weaviate
            if hasattr(response, "errors") and response.errors:
                logger.error(f"Erreurs Weaviate batch {batch_num}: {response.errors}")

        except Exception as e:
            failed += len(objects_to_insert)
            logger.error(f"Erreur insertion batch {batch_num} dans {file_path.name}: {e}")

    logger.info(f"Fin {file_path.name} : {total} chunks insérés, {failed} en échec")


def main():
    input_files = sorted(CHUNKS_DATA_DIR.glob(f"{CHUNKS_FILE_PATTERN}*.{JSONL_EXT}"))

    if not input_files:
        logger.info(f"Aucun fichier {CHUNKS_FILE_PATTERN}*.{JSONL_EXT} trouvé dans {CHUNKS_DATA_DIR}")
        return

    logger.info(f"{len(input_files)} fichiers trouvés dans {CHUNKS_DATA_DIR}")

    embeddings = get_embeddings()
    client = connect_client()

    try:
        weaviate_collection = get_collection(client)

        for file_path in input_files:
            ingest_file(weaviate_collection, embeddings, file_path)

        logger.info("Ingestion Weaviate terminée.")

    finally:
        client.close()


if __name__ == "__main__":
    main()
