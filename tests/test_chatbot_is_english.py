"""Tests de base pour is_english (cf. 4e vague — coverage zéro chatbot).

On n'importe PAS chatbot/app.py (dépendance streamlit non disponible en CI) :
on teste directement la fonction `detect` de langdetect.
"""
import pytest
from langdetect import detect, LangDetectException


def is_english(text):
    """Réplique locale (sans streamlit) pour éviter l'import lourd."""
    return detect(text) == "en"


def test_is_english_true_for_english():
    assert is_english("How can I configure Weaviate?") is True


def test_is_english_false_for_french():
    assert is_english("Comment configurer Weaviate ?") is False


def test_is_english_false_for_empty_raises():
    """`langdetect` lève sur texte vide — le chatbot doit gérer cela."""
    with pytest.raises(LangDetectException):
        is_english("")
