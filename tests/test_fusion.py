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


def test_fuse_orders_by_norm_score_desc():
    col_a = [_res(100, 0.5), _res(200, 0.6)]   # normés en interne -> 0.0, 1.0
    col_b = [_res(10, 0.7), _res(20, 0.8)]     # normés en interne -> 0.0, 1.0
    fused = fuse([col_a, col_b], top_k=3)
    assert len(fused) == 3
    # les deux "meilleurs" de chaque collection arrivent en tête
    assert fused[0]["norm_score"] == 1.0
    assert fused[1]["norm_score"] == 1.0
    # score de la collection A (le meilleur de A = 0.6) bat celui de B (0.8)
    # dans l'égalité 1.0/1.0, l'ordre relatif des deux meilleurs est arbitraire :
    # on vérifie seulement que les deux premiers sont des 1.0
    assert fused[0]["hybrid_score"] in (200, 20)


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
