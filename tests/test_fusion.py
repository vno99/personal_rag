# tests/test_fusion.py
from fusion import fuse, is_in_scope, normalize_minmax


def _res(hybrid, vector):
    return {"hybrid_score": hybrid, "vector_score": vector, "content": "x"}


def test_normalize_minmax_scales_to_0_1():
    results = [_res(10, 0.5), _res(20, 0.6), _res(30, 0.7)]
    out = normalize_minmax(results)
    assert out[0]["norm_score"] == 0.0
    assert out[1]["norm_score"] == 0.5
    assert out[2]["norm_score"] == 1.0
    assert len(out) == 3
    # les dicts d'entrée ne sont pas mutés
    assert "norm_score" not in results[0]


def test_normalize_minmax_flat_scores_are_all_one():
    results = [_res(15, 0.5), _res(15, 0.6)]
    out = normalize_minmax(results)
    assert out[0]["norm_score"] == 1.0
    assert out[1]["norm_score"] == 1.0


def test_fuse_drops_results_without_vector_score():
    """Sans `vector_score`, un résultat ne peut pas être retenu par
    `is_in_scope` (cf. code review #1). `fuse` l'exclut en amont pour
    éviter que son `norm_score=1.0` de repli ne pollue le tri fusionné.
    """
    col = [
        _res(10, 0.5),
        _res(20, 0.6),
        {"hybrid_score": 100, "vector_score": None, "content": "x"},
    ]
    fused = fuse([col], top_k=3)
    # Les deux résultats avec vector_score sont conservés et triés.
    assert len(fused) == 2
    assert fused[0]["hybrid_score"] == 20
    assert fused[1]["hybrid_score"] == 10


def test_fuse_orders_by_norm_score_desc():
    col_a = [_res(100, 0.5), _res(200, 0.6)]  # normés en interne -> 0.0, 1.0
    col_b = [_res(10, 0.7), _res(20, 0.8)]  # normés en interne -> 0.0, 1.0
    fused = fuse([col_a, col_b], top_k=3)
    assert len(fused) == 3
    # les deux "meilleurs" de chaque collection arrivent en tête (norm_score 1.0)
    assert fused[0]["norm_score"] == 1.0
    assert fused[1]["norm_score"] == 1.0
    # tie-break : col_b (vector 0.8) passe devant col_a (vector 0.6)
    assert fused[0]["hybrid_score"] == 20
    assert fused[1]["hybrid_score"] == 200


def test_fuse_respects_top_k():
    col_a = [_res(i, 0.5) for i in range(10)]
    fused = fuse([col_a], top_k=4)
    assert len(fused) == 4


def test_fuse_handles_empty_collections():
    assert fuse([[], []], top_k=3) == []


def test_is_in_scope_true_above_threshold():
    assert is_in_scope([_res(10, 0.5)])


def test_is_in_scope_false_below_threshold():
    assert not is_in_scope([_res(10, 0.4)])


def test_is_in_scope_false_on_empty():
    assert not is_in_scope([])


def test_is_in_scope_at_exact_threshold():
    """Le seuil MIN_VECTOR_SCORE = 0.45 est inclus (>=) ; au bord exact,
    le top-1 doit être validé (cf. code review B)."""
    assert is_in_scope([_res(10, 0.45)])
