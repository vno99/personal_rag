import config.config as config


def test_sources_is_list_of_dicts():
    assert isinstance(config.SOURCES, list)
    assert len(config.SOURCES) == 5
    assert all(isinstance(s, dict) for s in config.SOURCES)


def test_sources_have_required_keys():
    required = {"name", "type", "collection"}
    for source in config.SOURCES:
        assert required.issubset(source.keys())
        if source["type"] == "sitemap":
            assert "sitemap_url" in source
            assert "filter_urls" in source
        elif source["type"] == "git":
            assert "repo_url" in source
            assert "branch" in source
            assert "docs_path" in source
        elif source["type"] == "archive":
            assert "archive_url" in source


def test_source_names_unique():
    names = [s["name"] for s in config.SOURCES]
    assert len(names) == len(set(names))


def test_sources_by_type():
    types = {s["type"] for s in config.SOURCES}
    assert types == {"sitemap", "git", "archive"}


def test_get_source_returns_dict():
    assert config.get_source("typescript")["type"] == "git"


def test_get_source_unknown_raises():
    import pytest
    with pytest.raises(KeyError):
        config.get_source("inexistant")


def test_get_collection():
    assert config.get_collection("python") == "PythonDocs"


def test_status_constants():
    assert config.STATUS_DIR == "./data/status"
    assert config.RUNS_HISTORY == 10


def test_jsonl_ext_constant():
    """`JSONL_EXT` est utilisé par chunk_docs.py et ingest_weaviate.py
    pour le glob des fichiers : un changement de valeur casserait le
    pipeline silencieusement (cf. code review L).
    """
    assert config.JSONL_EXT == "jsonl"


def test_docs_and_chunks_patterns():
    """Les patterns dérivés du nom de source sont utilisés par les scripts
    de pipeline pour trouver leurs fichiers : un changement de format
    doit être explicite, pas accidentel.
    """
    assert config.docs_pattern("python") == "python_docs_batch_"
    assert config.chunks_pattern("python") == "python_chunks_batch_"
    assert config.docs_pattern("nextjs") == "nextjs_docs_batch_"
    assert config.chunks_pattern("nextjs") == "nextjs_chunks_batch_"
