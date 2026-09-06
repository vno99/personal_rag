import pytest
import ingest_weaviate
from ingest_weaviate import get_embeddings, read_jsonl_file, batch_iterable, run


class FakeStatus:
    def __init__(self):
        self.calls = []
    def progress(self, done, total):
        self.calls.append(("progress", done, total))
    def message(self, text):
        self.calls.append(("message", text))


def test_read_jsonl_file_empty(tmp_path):
    f = tmp_path / "empty.jsonl"
    f.write_text("\n\n", encoding="utf-8")
    assert list(read_jsonl_file(f)) == []


def test_batch_iterable_single():
    assert list(batch_iterable([42], 10)) == [[42]]


def test_get_embeddings():
    emb = get_embeddings()
    # Ne teste pas la qualité du modèle, juste que l'objet a embed_documents
    assert hasattr(emb, "embed_documents")
