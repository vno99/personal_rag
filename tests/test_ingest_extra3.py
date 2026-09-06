import pytest
import ingest_weaviate
from ingest_weaviate import get_collection


class FakeData:
    def __init__(self):
        self.inserted = 0
    def insert_many(self, objects):
        self.inserted += len(objects)
        return type("Resp", (), {"errors": None})()

class FakeColl:
    def __init__(self, name):
        self.name = name
        self.data = FakeData()

class FakeClient:
    def __init__(self, existing=None):
        self._collections = existing or {}
        self.collections = self  # Pour que client.collections.list_all() fonctionne
    def list_all(self):
        return list(self._collections.keys())
    def get(self, name):
        return self._collections.get(name)
    def create(self, **kwargs):
        name = kwargs.get("name")
        self._collections[name] = FakeColl(name)
        return self
    def close(self):
        pass


def test_get_collection_creates_new(monkeypatch):
    client = FakeClient()
    # Mock connect_client pour retourner notre fake
    monkeypatch.setattr(ingest_weaviate, "connect_client", lambda: client)
    monkeypatch.setattr(ingest_weaviate, "CHUNKS_DATA_DIR", type("P", (), {"glob": lambda *a, **k: []})())
    # On ne lance pas run complet, juste get_collection via le mock
    coll = get_collection(client, "NewColl")
    assert "NewColl" in client.list_all()
