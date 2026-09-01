# Chatbot Multi-Collections — Plan d'implémentation

> **Pour les agents exécutants :** SUB-SKILL REQUIS : utiliser `superpowers:subagent-driven-development` (recommandé) ou `superpowers:executing-plans` pour implémenter ce plan tâche par tâche. Les étapes utilisent la syntaxe à cocher (`- [ ]`).

**Goal :** Remplacer la sélection mono-collection du chatbot Streamlit par une **multi-sélection manuelle** des collections, avec N requêtes hybrides fusionnées par **min-max par collection** et seuil `MIN_VECTOR_SCORE` appliqué au top global.

**Architecture :** Le chatbot interroge chaque collection sélectionnée avec une requête hybride Weaviate (comme aujourd'hui), normalise les scores hybrides en [0,1] par collection (min-max), concatène et trie les résultats, puis applique le seuil vectoriel sur le top global. La logique de fusion est isolée dans une fonction pure testable (`fuse_collection_results`), séparée de l'UI Streamlit et des appels Weaviate.

**Tech Stack :** Streamlit, `weaviate-client` 4.21, `langchain_huggingface`, `pytest` (dev, nouveau).

**Spec :** `CLAUDE.md` → section « Évolution planifiée (non implémentée) » → « Phase A — Multi-sources » → « Chatbot — UX multi-collections ».

## Global Constraints

- La liste des collections du chatbot **doit rester synchronisée** avec les collections réellement ingérées par le pipeline (cf. points d'attention existants dans CLAUDE.md). Le chatbot garde sa propre constante `COLLECTIONS` (indépendance des deux mondes) — elle est mise à jour ici pour refléter les 5 sources : `SnowflakeDocs`, `DatabricksDocs`, `NextJSDocs`, `TypeScriptDocs`, `PythonDocs`.
- `WEAVIATE_HOST = "host.docker.internal"` et les ports restent codés en dur dans `chatbot/app.py` (hors périmètre).
- La logique de retrieval existante (`retrieve_context`, `extract_scores`, traduction) est conservée et adaptée : une requête par collection sélectionnée, puis fusion.
- `MIN_VECTOR_SCORE = 0.45` inchangé ; il s'applique au **top global** après fusion : si le meilleur score vectoriel du top fusionné est sous le seuil → message de repli.
- Les tests ne nécessitent ni Streamlit ni Weaviate : la fusion est testée sur des listes de dicts en mémoire.
- Pas de dépendance nouvelle en runtime : uniquement `pytest` en dev.

## File Structure

- Create: `chatbot/fusion.py` — fonctions pures de fusion (normalisation min-max, fusion multi-collections, application du seuil)
- Create: `tests/test_fusion.py` — tests unitaires de `chatbot/fusion.py` (racine `tests/`, réutilise `conftest.py` du plan pipeline en y ajoutant `chatbot/`)
- Modify: `chatbot/app.py` — UI multi-sélection + `retrieve_context` multi-collections

Responsabilités : `chatbot/fusion.py` ne contient que de la logique de fusion pure (aucune dépendance Streamlit/Weaviate) ; `chatbot/app.py` orchestre UI + retrieval ; les tests couvrent la fusion.

---

### Task 1: Infra de test pour `chatbot/` + fonction de fusion pure

**Files:**
- Create: `chatbot/fusion.py`
- Modify: `tests/conftest.py` (ajouter `chatbot/` au `sys.path`)
- Create: `tests/test_fusion.py`

**Interfaces:**
- Consumes: rien (nouveau module)
- Produces:
  - `fusion.normalize_minmax(results: list[dict], score_key: str = "hybrid_score") -> list[dict]` — retourne une **nouvelle liste** où chaque dict a `norm_score` dans [0,1] (min-max sur `score_key`). Si l'étendue est nulle (tous scores égaux), `norm_score = 1.0`. Les dicts ne sont pas mutés.
  - `fusion.fuse(results_by_collection: list[list[dict]], top_k: int = 3) -> list[dict]` — normalise chaque collection, concatène, trie par `norm_score` décroissant, garde `top_k`.
  - `fusion.is_in_scope(fused_top: list[dict] | None, min_vector_score: float = 0.45) -> bool` — True si `fused_top` non vide et `fused_top[0]["vector_score"] >= min_vector_score`.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# tests/conftest.py — ajouter à la fin (après APP_DIR)
CHATBOT_DIR = Path(__file__).resolve().parents[1] / "chatbot"
sys.path.insert(0, str(CHATBOT_DIR))
```

```python
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
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python -m pytest tests/test_fusion.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fusion'`

- [ ] **Step 3: Écrire `chatbot/fusion.py`**

```python
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
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_fusion.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add chatbot/fusion.py tests/conftest.py tests/test_fusion.py
git commit -m "feat(chatbot): fusion multi-collections (min-max) + tests"
```

---

### Task 2: Multi-sélection dans l'UI Streamlit

**Files:**
- Modify: `chatbot/app.py`

**Interfaces:**
- Consumes: `COL_NAME_LIST` (existant), `COLLECTIONS` (mis à jour)
- Produces: la variable de session `selected_collections` (liste) au lieu de `selected_collection` (chaîne) ; appel à `retrieve_context` avec `collections=selected_collections`

- [ ] **Step 1: Mettre à jour la liste `COLLECTIONS`**

Dans `chatbot/app.py`, remplacer la constante `COLLECTIONS` pour refléter les 5 sources ingérées par le pipeline (plan pipeline) :

```python
COLLECTIONS = [
    {
        "name": "SnowflakeDocs",
        "description": "Snowflake documentation : https://docs.snowflake.com"
    },
    {
        "name": "DatabricksDocs",
        "description": "Databricks documentation : https://docs.databricks.com/en"
    },
    {
        "name": "NextJSDocs",
        "description": "Next.js documentation : https://nextjs.org/docs"
    },
    {
        "name": "TypeScriptDocs",
        "description": "TypeScript documentation : https://www.typescriptlang.org/docs"
    },
    {
        "name": "PythonDocs",
        "description": "Python documentation : https://docs.python.org/3"
    },
]
```

- [ ] **Step 2: Remplacer les `st.pills` par un `st.multiselect`**

Dans la sidebar (`with st.sidebar:`), remplacer le bloc pills :

```python
            selected_collections = st.multiselect(
                "Collections à interroger",
                COL_NAME_LIST,
                default=COL_NAME_LIST,
                help="Sélectionnez une ou plusieurs collections. Par défaut : toutes.",
            )
```

- [ ] **Step 3: Adapter l'appel à `retrieve_context`**

Dans le bloc de réponse, remplacer l'appel unique par la liste :

```python
                    result = retrieve_context(
                        prompt,
                        top_k=top_num,
                        collections=selected_collections,
                    )
```

- [ ] **Step 4: Vérifier la cohérence du code**

Run: `python -c "import ast; ast.parse(open('chatbot/app.py').read())"`
Expected: PASSE. *On ne peut pas exécuter Streamlit ici ; la vérification est le parse + la review de cohérence (plus de référence à `selected_collection` au singulier).*

- [ ] **Step 5: Commit**

```bash
git add chatbot/app.py
git commit -m "feat(chatbot): multi-sélection des collections dans la sidebar"
```

---

### Task 3: `retrieve_context` multi-collections + seuil global

**Files:**
- Modify: `chatbot/app.py`

**Interfaces:**
- Consumes: `fusion.fuse`, `fusion.is_in_scope` (Task 1), `MIN_VECTOR_SCORE`, `ALPHA`, `HybridFusion.RELATIVE_SCORE`, `extract_scores` (existant), `translate_to_english`/`is_english` (existants)
- Produces:
  - `retrieve_context(query_text: str, top_k: int = 3, collections: list[str] | None = None) -> dict` — champ `collections` au lieu de `collection_name`. Retourne `{in_scope, reason, context, sources, debug}`. `debug` contient la liste fusionnée avec `norm_score`.

- [ ] **Step 1: Remplacer `retrieve_context`**

Dans `chatbot/app.py`, remplacer la fonction `retrieve_context` (et son `collection_name=COLLECTION_NAME` par défaut) par la version multi-collections :

```python
def query_one_collection(client, collection_name, query_text_en, query_vector, top_k):
    """Exécute une recherche hybride sur une collection et parse les résultats."""
    collection = client.collections.get(collection_name)

    response = collection.query.hybrid(
        query=query_text_en,
        vector=query_vector,
        alpha=ALPHA,
        limit=top_k,
        return_metadata=MetadataQuery(score=True, explain_score=True),
        fusion_type=HybridFusion.RELATIVE_SCORE,
    )

    results = []
    for obj in response.objects:
        props = obj.properties or {}
        explain_score = obj.metadata.explain_score or ""
        vector_score, keyword_score = extract_scores(explain_score)

        results.append({
            "collection": collection_name,
            "content": props.get("content", ""),
            "source": props.get("source", "N/A"),
            "hybrid_score": float(obj.metadata.score) if obj.metadata.score is not None else 0.0,
            "vector_score": vector_score,
            "keyword_score": keyword_score,
            "explain_score": explain_score,
        })

    return results


def retrieve_context(query_text, top_k=TOP_K, collections=None):
    """
    Recherche hybride multi-collections avec fusion min-max par collection.

    Args:
        query_text (str): La requête (auto-traduite en anglais si besoin).
        top_k (int, optional): Nombre de résultats à garder après fusion.
            Defaults to TOP_K.
        collections (list[str], optional): Noms des collections à interroger.
            Defaults to [COLLECTION_NAME].

    Returns:
        dict: 'in_scope' (bool), 'reason' (str), 'context' (str),
              'sources' (list), 'debug' (list, résultats fusionnés).
    """
    if collections is None:
        collections = [COLLECTION_NAME]

    query_text_en = translate_to_english(query_text) if not is_english(query_text) else query_text
    query_vector = embeddings.embed_query(query_text_en)
    client = connect_client()

    try:
        results_by_collection = [
            query_one_collection(client, name, query_text_en, query_vector, top_k)
            for name in collections
        ]

        fused = fuse(results_by_collection, top_k=top_k)

        if not fused:
            return {
                "in_scope": False,
                "reason": "no_results",
                "context": "",
                "sources": [],
                "debug": [],
            }

        if not is_in_scope(fused, min_vector_score=MIN_VECTOR_SCORE):
            top1 = fused[0]["vector_score"]
            return {
                "in_scope": False,
                "reason": f"vector_score_too_low ({top1} < {MIN_VECTOR_SCORE})",
                "context": "",
                "sources": [],
                "debug": fused,
            }

        context = "\n\n".join([r["content"] for r in fused if r.get("content")])
        sources = [r["source"] for r in fused]

        return {
            "in_scope": True,
            "reason": "ok",
            "context": context,
            "sources": sources,
            "debug": fused,
        }

    finally:
        client.close()
```

- [ ] **Step 2: Vérifier le parse**

Run: `python -c "import ast; ast.parse(open('chatbot/app.py').read())"`
Expected: PASSE. *L'exécution complète nécessite Streamlit + Weaviate + les modèles — vérification manuelle en Task 4.*

- [ ] **Step 3: Commit**

```bash
git add chatbot/app.py
git commit -m "feat(chatbot): retrieve_context multi-collections avec fusion min-max"
```

---

### Task 4: Smoke test manuel du chatbot

**Files:**
- Aucun (vérification)

- [ ] **Step 1: Lancer les tests unitaires**

Run: `python -m pytest tests/test_fusion.py -v`
Expected: PASS (8 tests)

- [ ] **Step 2: Lancer le chatbot avec Weaviate up**

Run: `cd chatbot && streamlit run app.py` (Weaviate local requis : `docker-compose up -d` à la racine)
Expected: l'app démarre ; la sidebar affiche le multiselect des 5 collections, toutes cochées par défaut

- [ ] **Step 3: Interroger**

Pose une question de type « How to configure a warehouse in Snowflake ? ».
Expected: une réponse générée ; l'expander « 📚 Sources » affiche les sources ; le multiselect permet de restreindre à une seule collection et de constater la différence.

- [ ] **Step 4: Vérifier le repli**

Pose une question hors-sujet (« What is the capital of France ? »).
Expected: le message de repli apparaît (top global sous `MIN_VECTOR_SCORE`).

- [ ] **Step 5: Commit final si ajustements UI**

```bash
git add chatbot/app.py
git commit -m "fix(chatbot): ajustements UI après smoke test"
```

---

## Self-Review

**1. Spec coverage (CLAUDE.md → Phase A → UX multi-collections) :**
- Multi-sélection manuelle (multiselect, « toutes » par défaut) → Task 2 ✅
- N requêtes hybrides (une par collection sélectionnée) → Task 3 (`query_one_collection` appelé par collection) ✅
- Fusion min-max par collection → Task 1 (`normalize_minmax` + `fuse`) ✅
- Seuil `MIN_VECTOR_SCORE` sur le top global → Task 1 (`is_in_scope`) + Task 3 ✅
- `COLLECTIONS` synchronisée avec 5 sources ingérées → Task 2 ✅
- Remplacement des `st.pills` mono-sélection → Task 2 ✅

**2. Placeholder scan :** aucun « TBD/TODO » ; chaque étape contient le code exact. Les étapes de smoke test sont des vérifications manuelles explicites, pas des placeholders.

**3. Type consistency :** `normalize_minmax`/`fuse`/`is_in_scope` définis en Task 1 et consommés en Task 3 avec les mêmes signatures. `retrieve_context` expose `collections` (liste) ; `query_one_collection` retourne des dicts avec `collection`, `content`, `source`, `hybrid_score`, `vector_score`, `keyword_score`, `explain_score` — `fuse` lit `hybrid_score`, `is_in_scope` lit `vector_score` : les clés correspondent. `selected_collections` (Task 2) est passé en `collections` (Task 3) — cohérent.
