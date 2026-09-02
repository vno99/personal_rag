import chunk_docs
import pytest
from chunk_docs import chunk_one_record, make_chunk_id


class _FakeStatus:
    """Objet minimal compatible avec l'instrumentation (progress/message no-op)."""

    def __init__(self):
        self.calls = []

    def progress(self, done, total):
        self.calls.append(("progress", done, total))

    def message(self, text):
        self.calls.append(("message", text))


class FakeSplitter:
    def split_text(self, text: str):
        # découpe grossièrement en blocs de 10 caractères
        return [text[i : i + 10] for i in range(0, len(text), 10)]


class FakeTokenizer:
    def encode(self, text: str, **kwargs):
        return list(range(len(text)))


def test_make_chunk_id_is_deterministic():
    a = make_chunk_id("src", 3, "contenu")
    b = make_chunk_id("src", 3, "contenu")
    assert a == b
    assert len(a) == 40  # SHA-1 hex


def test_make_chunk_id_changes_with_content():
    assert make_chunk_id("src", 3, "a") != make_chunk_id("src", 3, "b")


def test_chunk_one_record_with_injected_splitter():
    record = {"source": "s", "loc": "l", "lastmod": "2026-01-01", "content": "0123456789ABCDEF"}
    chunks = chunk_one_record(record, splitter=FakeSplitter(), tokenizer=FakeTokenizer())
    assert len(chunks) == 2
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["source"] == "s"
    assert chunks[1]["chunk_index"] == 1


def test_chunk_one_record_skips_empty_content():
    record = {"source": "s", "content": "   "}
    assert chunk_one_record(record, splitter=FakeSplitter(), tokenizer=FakeTokenizer()) == []


def test_run_raises_with_status_when_no_raw(monkeypatch, tmp_path):
    monkeypatch.setattr(chunk_docs, "RAW_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="aucun fichier"):
        chunk_docs.run("zz_inexistant", status=_FakeStatus())


def test_run_returns_without_status_when_no_raw(monkeypatch, tmp_path):
    monkeypatch.setattr(chunk_docs, "RAW_DIR", tmp_path)
    chunk_docs.run("zz_inexistant")  # comportement CLI : ne doit pas lever
