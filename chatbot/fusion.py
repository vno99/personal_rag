"""Fusion des résultats de recherche multi-collections.

Logique pure (aucune dépendance Streamlit/Weaviate) pour pouvoir être
testée unitairement.
"""


def normalize_minmax(results, score_key="hybrid_score"):
    """Normalise les scores de `results` en [0,1] par min-max.

    Args:
        results (list[dict]): Résultats d'une même collection, chacun
            avec `score_key`.
        score_key (str): Clé du score à normaliser.

    Returns:
        list[dict]: Nouvelle liste avec un champ `norm_score` ajouté.
            Les dicts d'entrée ne sont pas modifiés.
    """
    scores = [r[score_key] for r in results if r.get(score_key) is not None]
    if not scores:
        return [dict(r, norm_score=1.0) for r in results]

    low = min(scores)
    high = max(scores)
    span = high - low

    out = []
    for r in results:
        score = r.get(score_key)
        if score is None or span == 0:
            out.append(dict(r, norm_score=1.0))
        else:
            out.append(dict(r, norm_score=(score - low) / span))
    return out


def fuse(results_by_collection, top_k=3):
    """Normalise chaque collection, concatène, trie par `norm_score` décroissant.

    Args:
        results_by_collection (list[list[dict]]): Une liste par collection,
            chaque dict ayant `hybrid_score` (et `vector_score` pour le seuil).
        top_k (int): Nombre de résultats à garder après fusion.

    Returns:
        list[dict]: Résultats fusionnés et triés, chaque dict ayant `norm_score`.
    """
    normalized = [
        item
        for collection in results_by_collection
        for item in normalize_minmax(collection)
    ]
    normalized.sort(key=lambda r: r["norm_score"], reverse=True)
    return normalized[:top_k]


def is_in_scope(fused_top, min_vector_score=0.45):
    """Le top fusionné est-il assez pertinent pour répondre ?

    Args:
        fused_top (list[dict] | None): Résultats fusionnés (déjà triés).
        min_vector_score (float): Seuil sur le score vectoriel brut du top-1.

    Returns:
        bool: True si le top-1 a un `vector_score` >= seuil.
    """
    if not fused_top:
        return False
    top1_vector_score = fused_top[0].get("vector_score")
    return top1_vector_score is not None and top1_vector_score >= min_vector_score
