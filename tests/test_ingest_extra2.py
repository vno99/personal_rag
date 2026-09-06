import pytest
import json
from pathlib import Path
import ingest_weaviate
from ingest_weaviate import ingest_file, get_collection, get_embeddings


class FakeResponse:
    def __init__(self, errors=None):
        self.errors = errors


class FakeData:
    def __init__(self):
        self.inserted = 0
    def insert_many(self, objects):
        self.inserted += len(objects)
        return FakeResponse(errors=None)

class FakeCollection:
    def __init__(self):
        self.data = FakeData()


class FakeClient:
    def __init__(self, collections=None):
        self._collections = collections or {}

    def collections(self):
        return self

    def list_all(self):
        return list(self._collections.keys())

    def get(self, name):
        return self._collections.get(name)

    def create(self, **kwargs):
        name = kwargs.get("name")
        self._collections[name] = FakeCollection()
        return self

    def close(self):
        pass


def test_ingest_file_inserts(monkeypatch, tmp_path):
    fake_coll = FakeCollection()
    emb = type("Emb", (), {"embed_documents": lambda self, texts: [[0.1]*10 for _ in texts]})()
    monkeypatch.setattr(ingest_weaviate, "get_embeddings", lambda: emb)

    chunk_file = tmp_path / "chunks_test.jsonl"
    chunk_file.write_text(json.dumps({"chunk_id": "c1", "content": "hello", "source": "s"}) + "\n", encoding="utf-8")

    ingest_file(fake_coll, emb, chunk_file)
    assert fake_coll.data.inserted > 0
