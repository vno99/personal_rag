"""Tests de base pour is_english (réplique locale, sans dépendance chatbot/app.py)."""
import pytest

pytest.importorskip("langdetect", reason="langdetect non disponible en CI")

from langdetect import detect, LangDetectException


def is_english(text):
    """Réplique locale du comportement réel (chatbot/app.py lignes 101-104)."""
    try:
        return detect(text) == "en"
    except Exception:
        return False


def test_is_english_true_for_english():
    assert is_english("How can I configure Weaviate?") is True


def test_is_english_false_for_french():
    assert is_english("Comment configurer Weaviate et gérer les embeddings vectoriels dans la base ?") is False


def test_is_english_false_for_empty():
    """Le vrai is_english capte l'exception et retourne False (cf. chatbot/app.py)."""
    assert is_english("") is False


def test_is_english_raises_for_empty_on_raw_detect():
    """Le détecteur brut lève sur texte vide, mais is_english le masque."""
    with pytest.raises(LangDetectException):
        detect("")
