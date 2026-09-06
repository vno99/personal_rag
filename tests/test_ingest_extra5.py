import json
from unittest.mock import MagicMock

import ingest_weaviate


def test_get_collection_existing(monkeypatch):
    # Couvre lignes 48 (collection existante dans get_collection)
    fake_coll = MagicMock()
    fake_coll.name = "ExistingColl"
    client = MagicMock()
    client.collections.list_all.return_value = ["ExistingColl"]
    client.collections.get.return_value = fake_coll
    monkeypatch.setattr(ingest_weaviate, "connect_client", lambda: client)
    result = ingest_weaviate.get_collection(client, "ExistingColl")
    assert result == fake_coll
    client.collections.create.assert_not_called()


def test_ingest_file_with_missing_chunk_id(monkeypatch, tmp_path):
    # Couvre lignes 181-183 (chunk_id manquant)
    fake_coll = MagicMock()
    fake_coll.data.insert_many.side_effect = lambda objs: type("R", (), {"errors": None})()
    monkeypatch.setattr(
        ingest_weaviate, "get_embeddings", lambda: MagicMock(embed_documents=lambda texts: [[0.1] * 10 for _ in texts])
    )
    chunk_file = tmp_path / "missing.jsonl"
    chunk_file.write_text(json.dumps({"content": "hello"}) + "\n", encoding="utf-8")
    ingest_weaviate.ingest_file(
        fake_coll, MagicMock(embed_documents=lambda texts: [[0.1] * 10 for _ in texts]), chunk_file
    )
    # Le chunk sans chunk_id est ignoré, insert_many n'est pas appelé
    fake_coll.data.insert_many.assert_not_called()
