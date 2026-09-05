"""Parseur d'`explain_score` Weaviate.

Logique pure (aucune dépendance Streamlit/Weaviate) pour pouvoir être
testée unitairement. Le format d'`explain_score` est un texte libre
renvoyé par Weaviate ; si Weaviate change son format, le parseur retourne
silencieusement `None` et la fusion multi-collections dégrade. Le contrat
est verrouillé par `tests/test_extract_scores.py`.
"""
import re


def extract_scores(explain_score: str):
    """Extrait les scores bruts vector et keyword du texte `explain_score`.

    Args:
        explain_score (str): Le texte renvoyé par Weaviate (peut être vide).

    Returns:
        tuple[float | None, float | None]: `(vector_score, keyword_score)`.
            Chaque score vaut `None` si la ligne correspondante est absente.

    Raises:
        ValueError: Si une ligne ressemble au pattern mais que le score n'est
            pas un float — on préfère propager l'erreur plutôt que masquer
            une régression de format en retournant `None` silencieusement.
    """
    if not explain_score:
        return None, None

    vector_match = re.search(
        r"Result Set vector,?\s*hybridVector.*?original score ([0-9.]+)",
        explain_score,
        flags=re.IGNORECASE | re.DOTALL,
    )
    keyword_match = re.search(
        r"Result Set keyword,?\s*bm25.*?original score ([0-9.]+)",
        explain_score,
        flags=re.IGNORECASE | re.DOTALL,
    )

    vector_score = float(vector_match.group(1)) if vector_match else None
    keyword_score = float(keyword_match.group(1)) if keyword_match else None

    return vector_score, keyword_score
