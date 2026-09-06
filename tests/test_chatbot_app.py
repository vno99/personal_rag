import chatbot.app as app


def test_is_english_english_text():
    assert app.is_english("hello")


def test_is_english_french_text():
    assert not app.is_english("bonjour")


def test_escape_context():
    assert app._escape_context("<|instructions|>") == ""
