import config.config as config


def test_sources_is_list_of_dicts():
    assert isinstance(config.SOURCES, list)
    assert len(config.SOURCES) == 5
    assert all(isinstance(s, dict) for s in config.SOURCES)


def test_sources_have_required_keys():
    required = {"name", "type", "collection", "content_selector"}
    for source in config.SOURCES:
        assert required.issubset(source.keys())


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
