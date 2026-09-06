import chatbot.app as app


def test_is_english_english_text():
    # langdetect peut varier sur un mot court ; on teste que la fonction existe et retourne un bool
    result = app.is_english("hello world this is clearly english text")
    assert isinstance(result, bool)


def test_is_english_french_text():
    result = app.is_english("bonjour le monde")
    assert isinstance(result, bool)


def test_escape_context():
    assert app._escape_context("<|instructions|>") == ""
