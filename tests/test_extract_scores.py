# tests/test_extract_scores.py
"""Fige le contrat de `extract_scores` (parsing de l'explain_score Weaviate).

Le format d'`explain_score` est un texte libre renvoyé par Weaviate ; si Weaviate
change son format, le parseur retourne silencieusement `None` et la fusion
multi-collections dégrade (cf. code review #1 et #4). Ce test verrouille le
contrat de surface pour qu'un changement soit détecté par la CI plutôt qu'en
production.
"""

import pytest
from extract_scores import extract_scores

# --- Contrat de base --------------------------------------------------------


def test_empty_string_returns_none_tuple():
    assert extract_scores("") == (None, None)


def test_none_returns_none_tuple():
    assert extract_scores(None) == (None, None)


def test_unrelated_text_returns_none_tuple():
    assert extract_scores("nothing relevant here") == (None, None)


# --- Cas conforme au format Weaviate observé --------------------------------

VECTOR_LINE = (
    'Result Set vector, hybridVector: Property "content" (0.85), Property "chunk_id" (0.0) original score 0.789'
)
KEYWORD_LINE = 'Result Set keyword, bm25: Property "content" (1.20), Property "chunk_id" (0.0) original score 0.345'


def test_vector_and_keyword_extracted():
    explain = VECTOR_LINE + "\n" + KEYWORD_LINE
    vector, keyword = extract_scores(explain)
    assert vector == pytest.approx(0.789)
    assert keyword == pytest.approx(0.345)


def test_only_vector_line_present():
    vector, keyword = extract_scores(VECTOR_LINE)
    assert vector == pytest.approx(0.789)
    assert keyword is None


def test_only_keyword_line_present():
    vector, keyword = extract_scores(KEYWORD_LINE)
    assert vector is None
    assert keyword == pytest.approx(0.345)


def test_lowercase_fragments_still_match():
    """Weaviate peut renvoyer `result set vector` en minuscules ; le flag
    `re.IGNORECASE` doit continuer à matcher (sinon vector_score=None partout).
    """
    explain = VECTOR_LINE.lower()
    vector, _ = extract_scores(explain)
    assert vector == pytest.approx(0.789)


# --- Robustesse -------------------------------------------------------------


def test_malformed_score_raises():
    """Si la ligne ressemble au pattern mais que le score n'est pas un float,
    `float(...)` doit lever — et le caller doit voir l'erreur (pas un None
    silencieux qui masquerait la régression).
    """
    # "1.2.3.4" matche `[0-9.]+` mais n'est pas un float valide.
    explain = "Result Set vector, hybridVector original score 1.2.3.4"
    with pytest.raises(ValueError):
        extract_scores(explain)
