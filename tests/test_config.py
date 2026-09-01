import config.config as config


def test_sources_is_list_of_dicts():
    assert isinstance(config.SOURCES, list)
    assert len(config.SOURCES) == 5
    assert all(isinstance(s, dict) for s in config.SOURCES)
