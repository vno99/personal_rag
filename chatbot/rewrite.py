"""Réécriture de la question utilisateur en requête de recherche descriptive.

Module PUR (aucune dépendance Streamlit/OpenRouter/Weaviate) pour être
testable unitairement. L'appel réseau au LLM est réalisé dans `app.py` ;
ce module fournit la construction des messages et le parsing de la réponse.
"""

_SYSTEM_PROMPT = (
    "You rewrite a user's question into an optimal English search query for a "
    "retrieval system over technical documentation (Snowflake, Databricks, "
    "Next.js, TypeScript, Python)."
)

# Marqueurs de page d'erreur HTTP que le traducteur Google (deep_translator)
# peut renvoyer *en guise de traduction* au lieu de lever une exception.
_TRANSLATION_ERROR_MARKERS = (
    "server error",
    "that's an error",
    "that’s an error",
    "please try again",
    "that's all we know",
    "bad gateway",
    "error 500",
    "error 502",
    "error 403",
    "forbidden",
)


def is_plausible_translation(text, original: str | None = None) -> bool:
    """Une sortie de traduction est-elle vraisemblable (sinon page d'erreur) ?

    Google Translate (via `deep_translator`) renvoie parfois une page d'erreur
    HTTP (ex. « Error 500 (Server Error)!!1500.That's an error.... ») sous forme
    de *texte* au lieu de lever une exception : sans validation, ce texte
    parasite polluerait la reformulation puis le retrieval.

    Args:
        text: Sortie du traducteur (str | None).
        original (str | None): Texte source, pour borner la longueur attendue.

    Returns:
        bool: True si la sortie ressemble à une vraie traduction.
    """
    if not text or not text.strip():
        return False
    lowered = text.lower()
    if any(marker in lowered for marker in _TRANSLATION_ERROR_MARKERS):
        return False
    # Une page d'erreur est très longue par rapport à la question source.
    return not (original and len(text) > 4 * len(original) + 60)


def build_rewrite_messages(question_en: str) -> list[dict]:
    """Construit les messages système + utilisateur pour la réécriture.

    Args:
        question_en (str): Question (idéalement en anglais, après traduction).

    Returns:
        list[dict]: Messages au format OpenAI ([{role, content}, ...]).
    """
    user = (
        "Rewrite the following question into a concise English search query "
        "(one sentence, 5-20 words) that best matches documentation pages that "
        "would answer it.\n"
        "Rules:\n"
        "- If the question is not in English, first translate it to English.\n"
        "- The output must be English.\n"
        "- Keep any code, SQL keywords, function names, identifiers and version "
        "numbers verbatim.\n"
        "- Broad 'what is X' / 'how does X work' questions must target "
        "explanatory pages: mention 'overview', 'introduction', 'key concepts' "
        "or 'architecture'. Never steer the query toward release notes or "
        "changelogs.\n"
        "- Precise technical questions: return them (almost) unchanged.\n"
        "- Reply with only the search query. No quotes, no explanation, no "
        "code fences.\n\n"
        "Examples:\n"
        "QUESTION: what is snowflake?\n"
        "SEARCH QUERY: Snowflake overview introduction key concepts architecture\n\n"
        "QUESTION: resume a suspended warehouse with SQL\n"
        "SEARCH QUERY: resume a suspended warehouse with SQL\n\n"
        f"QUESTION: {question_en}\n"
        "SEARCH QUERY:"
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def parse_search_query(raw, fallback: str) -> str:
    """Extrait la requête de recherche de la réponse du modèle.

    Gère les réponses bavardes (on garde la dernière ligne non vide), les
    backticks / guillemets / fences. Retourne `fallback` si rien d'exploitable.

    Args:
        raw: Réponse brute du modèle (str | None).
        fallback (str): Requête à renvoyer si l'extraction échoue
            (généralement la question originale).

    Returns:
        str: La requête de recherche extraite.
    """
    if not raw:
        return fallback
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return fallback
    query = lines[-1]
    query = query.strip("`\"'")  # backticks ou guillemets autour de la requête
    return query if query else fallback
