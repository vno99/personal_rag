import app.query_weaviate as qw


def test_constants():
    assert qw.QUERY_TEXT == "What is Unity Catalog?"
    assert qw.LIMIT == 3
