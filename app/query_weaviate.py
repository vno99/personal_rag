import argparse

import config.config as config
import weaviate
from langchain_huggingface import HuggingFaceEmbeddings
from weaviate.classes.query import MetadataQuery, Filter

QUERY_TEXT = "What is Unity Catalog?"
LIMIT = 3


def main():
    parser = argparse.ArgumentParser(description="Test jetable de la recherche hybride")
    parser.add_argument(
        "--collection",
        default=config.get_collection(config.SOURCES[0]["name"]),
        help="Collection Weaviate à interroger",
    )
    args = parser.parse_args()

    embeddings = HuggingFaceEmbeddings(
        model_name=config.EMBEDDING_MODEL_NAME,
        model_kwargs={"device": config.EMBEDDING_DEVICE},
        encode_kwargs={"normalize_embeddings": config.NORMALIZE_EMBEDDINGS},
    )

    query_vector = embeddings.embed_query(QUERY_TEXT)

    client = weaviate.connect_to_local(
        host=config.WEAVIATE_HOST,
        port=config.WEAVIATE_PORT,
        grpc_port=config.WEAVIATE_GRPC_PORT,
    )

    try:
        collection = client.collections.get(args.collection)

        response = collection.query.hybrid(
            query=QUERY_TEXT,
            vector=query_vector,
            alpha=0.5,
            limit=LIMIT,
        )

        print(f"\n🔎 Query: {QUERY_TEXT}\n")

        if not response.objects:
            print("Aucun résultat.")
            return

        for i, obj in enumerate(response.objects, start=1):
            props = obj.properties
            print(f"{'=' * 80}")
            print(f"Résultat #{i}")
            print(f"Source      : {props.get('source')}")
            print(f"Loc         : {props.get('loc')}")
            print(f"Chunk index : {props.get('chunk_index')}")
            print(f"Distance    : {obj.metadata.distance}")
            print(f"Contenu     : {props.get('content', '')[:500]}")
            print()

    finally:
        client.close()


if __name__ == "__main__":
    main()
