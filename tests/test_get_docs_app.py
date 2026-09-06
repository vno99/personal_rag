from get_docs import EXTRACTORS


def test_extractor_mapping():
    assert "sitemap" in EXTRACTORS
    assert "archive" in EXTRACTORS
