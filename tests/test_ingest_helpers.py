import json

from ingest_weaviate import batch_iterable, read_jsonl_file


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
