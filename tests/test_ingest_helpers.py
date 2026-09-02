import json
from types import SimpleNamespace

from ingest_weaviate import batch_iterable, ingest_file, read_jsonl_file


def test_batch_iterable_yields_full_batches():
    batches = list(batch_iterable(range(10), 3))
    assert batches == [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]


def test_batch_iterable_empty():
    assert list(batch_iterable([], 3)) == []


def test_read_jsonl_file(tmp_path):
    f = tmp_path / "data.jsonl"
    f.write_text(
        '{"a": 1}\n\n{"a": 2}\n',  # ligne vide ignorée
        encoding="utf-8",
    )
    records = list(read_jsonl_file(f))
    assert len(records) == 2
    assert records[0]["a"] == 1


class _FakeData:
    def __init__(self):
        self.inserted = []

    def insert_many(self, objects):
        self.inserted.append(len(objects))
        return SimpleNamespace(errors=None)


class _FakeColl:
    def __init__(self):
        self.data = _FakeData()


class _FakeEmb:
    def embed_documents(self, texts):
        return [[0.1, 0.2] for _ in texts]


def test_ingest_file_reports_progress_per_batch(tmp_path):
    lines = "\n".join(f'{{"chunk_id": "c{i}", "content": "contenu {i}"}}' for i in range(250))
    (tmp_path / "chunks.jsonl").write_text(lines, encoding="utf-8")
    coll = _FakeColl()
    calls = []
    ingest_file(coll, _FakeEmb(), tmp_path / "chunks.jsonl", progress=lambda n: calls.append(n))
    assert calls == [100, 100, 50]
    assert coll.data.inserted == [100, 100, 50]
