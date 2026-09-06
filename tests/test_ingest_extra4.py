from unittest.mock import MagicMock

import ingest_weaviate


def test_run_mock(monkeypatch, tmp_path):
    # Couvre le chemin run avec mocks complets
    monkeypatch.setattr(ingest_weaviate, "CHUNKS_DATA_DIR", tmp_path)
    monkeypatch.setattr(ingest_weaviate.config, "chunks_pattern", lambda s: "test_")
    monkeypatch.setattr(ingest_weaviate.config, "JSONL_EXT", "jsonl")
    monkeypatch.setattr(ingest_weaviate.config, "get_collection", lambda s: "CollName")

    # Créer un fichier chunks temporaire
    (tmp_path / "test_batch_001.jsonl").write_text('{"chunk_id":"c1","content":"hello"}\n', encoding="utf-8")

    # Mock embeddings et client
    fake_emb = MagicMock()
    fake_emb.embed_documents.side_effect = lambda texts: [[0.1]*10 for _ in texts]

    monkeypatch.setattr(ingest_weaviate, "get_embeddings", lambda: fake_emb)
    monkeypatch.setattr(ingest_weaviate, "connect_client", lambda: MagicMock())
    monkeypatch.setattr(ingest_weaviate, "get_collection", lambda c, name: MagicMock())

    # Mock ingest_file pour éviter l'appel réel
    monkeypatch.setattr(ingest_weaviate, "ingest_file", lambda *args, **kw: None)

    ingest_weaviate.run("test_source", status=None)
