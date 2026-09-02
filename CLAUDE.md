# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Vue d'ensemble

Application de **RAG (Retrieval-Augmented Generation)** personnelle : elle indexe de la documentation technique dans **Weaviate** et la rend interrogable via un chatbot **Streamlit**. La recherche est **hybride** (dense + BM25/sparse), fusionnée par Weaviate avec un `alpha=0.7`. Embeddings `sentence-transformers/all-mpnet-base-v2` générés côté client (HuggingFace), LLM de génération `mistral-large-latest`.

Le repo est découpé en **deux mondes indépendants** :

| Composant | Dossier | Rôle |
|---|---|---|
| Pipeline d'ingestion | `app/` | Extraction → chunking → embedding → indexation Weaviate |
| Interface chatbot | `chatbot/` | App Streamlit, retrieval + génération |

Le répertoire `data/` contient les fichiers intermédiaires (`raw/` = docs bruts, `chunks/` = chunks) au format JSONL — **ignorés par git** (`/data/**/*.jsonl`).

## Évolution planifiée

Direction validée en brainstorming (sept. 2026). La **Phase A** est **implémentée** dans ses deux volets :

- **Multi-sources (pipeline)** — voir `app/config/config.py`, `app/extractors/`, `app/get_docs.py`, `app/chunk_docs.py`, `app/ingest_weaviate.py`.
- **Chatbot UX multi-collections** — voir `chatbot/app.py`, `chatbot/fusion.py`, `tests/test_fusion.py`.

Reste **non implémentée** : la **Phase B** (administration).

### Phase A — Multi-sources (pipeline) — IMPLÉMENTÉE

- **`app/config/config.py`** : liste **`SOURCES`** data-driven. Chaque source porte : `name`, `type` (extraction), URL, pattern de fichiers dérivé du nom, `collection`, `content_selector`.
- **Trois mécaniques d'extraction** derrière une **classe abstraite `BaseExtractor`** (`app/extractors/`) avec héritage — `SitemapExtractor`, `GitExtractor`, `ArchiveExtractor` implémentent une interface commune `extract()` → JSONL. `get_docs.py` est un dispatcher qui instancie la classe selon `source['type']`. Ajouter une source d'un nouveau type = ajouter un extracteur.
  | Source | Type | Classe | Mécanique |
  |---|---|---|---|
  | Snowflake, Databricks, Next.js | `sitemap` | `SitemapExtractor` | `SitemapLoader` |
  | TypeScript | `git` | `GitExtractor` | cloner `microsoft/TypeScript-Website` (branch `v2`), lire les `.md` de `packages/documentation/copy/en/` |
  | Python | `archive` | `ArchiveExtractor` | télécharger `https://docs.python.org/3.14/archives/python-3.14-docs-html.zip` (~17 Mo), extraire, parser les HTML |
- **Extraction HTML généralisée** : le sélecteur de contenu est un paramètre de la source (`content_selector`) — `article` pour la plupart, `[role='main']` pour la doc Python (Sphinx).
- **Java : écarté pour l'instant** (API Javadoc trop volumineuse, pas de sitemap exploitable).

### Phase A — Chatbot UX multi-collections (implémentée)

- **`chatbot/app.py`** : `COLLECTIONS` compte 5 entrées (Snowflake, Databricks, Next.js, TypeScript, Python). Sélection **manuelle multi-collections** dans la sidebar (`st.multiselect`, « toutes » par défaut). Le retrieval fait **N requêtes hybrides** (une par collection sélectionnée ; les collections configurées mais non encore ingérées en base sont ignorées), puis délègue la fusion à `chatbot/fusion.py`.
- **`chatbot/fusion.py`** : logique de fusion **pure** (sans dépendance Streamlit/Weaviate, testable unitairement). **Fusion min-max par collection** (`normalize_minmax`, scores normalisés en [0,1]), concaténation et tri par `norm_score` décroissant avec **tie-break `vector_score`** (`fuse`). Le seuil `MIN_VECTOR_SCORE` s'applique sur le **top fusionné** : `is_in_scope` ne valide que si le `vector_score` brut du top-1 global est ≥ seuil, sinon l'app renvoie un message de repli.
- **Tests** : `tests/test_fusion.py` couvre `normalize_minmax`, `fuse` et `is_in_scope` (voir la section Commandes).

### Phase B — Administration (app Streamlit séparée)

- **Nouvelle app Streamlit dédiée** (pas une page de `chatbot/app.py`) qui pilote le pipeline.
- **Lancement en sous-processus** : l'app appelle les scripts d'ingestion via `subprocess`, avec statut/log lu depuis un fichier — l'UI reste réactive pendant l'ingestion.
- **Fichier de statut par run** : un fichier JSON par run dans `data/status/` (nommé par timestamp, ex: `2026-09-01T14-30-05_typescript.json`), plus un pointeur `latest.json` vers le run le plus récent. **Un run = une source** (`operation`: ingest | purge | chunk). Les scripts écrivent via un utilitaire partagé (`status_writer`). Contenu : `run_id`, `source`, `operation`, `status` (running/done/failed/cancelled), `pid` (pour kill), timestamps, `step` (get_docs/chunk_docs/ingest_weaviate/cleanup), `step_progress` (`{done, total}`), `last_message`, `error`. Historique limité aux derniers N runs (ex: 10).
- **Planification : manuelle uniquement** pour l'instant (pas de scheduler).
- **Stratégie de fraîcheur hybride** (le cœur du « cycle de vie ») :
  - **Weaviate comme source de vérité** : il stocke déjà `lastmod` et `source` par objet → pas de manifeste séparé.
  - **Diff du signal de changement par type de source** : `lastmod` (sitemap), hash de commit/date du fichier (git), version/hash du zip (archive).
  - **Chemin principal** : ne re-télécharger/re-embedder que les pages modifiées ; supprimer les pages disparues (par `source`, objets dont le `chunk_id` n'est plus dans le nouveau set de chunks).
  - **Fallback** : re-téléchargement complet si le signal de changement est absent/peu fiable — le diff des chunks contre Weaviate reste valide (pas de ré-embedding massif).

## Architecture

### Pipeline d'ingestion (`app/`) — un script = une étape, exécutés séquentiellement

Tous les scripts font `import config.config as config` : **`app/config/config.py` est la source unique de vérité** pour la source de docs, les noms de fichiers, la collection Weaviate, la taille des chunks, le modèle d'embedding, etc. Les scripts doivent être lancés **depuis la racine du repo** (`python app/<script>.py`) : les imports `config.*` résolvent `app/`, mais les chemins de données (`./data/...`) sont relatifs.

1. **`get_docs.py`** — dispatcher `--source <name>` : instancie l'extracteur correspondant au `type` de la source (`sitemap` → `SitemapExtractor`, `git` → `GitExtractor`, `archive` → `ArchiveExtractor`, cf. `app/extractors/`) et sauvegarde les docs par lots de `BATCH_SIZE_DOCS` dans `data/raw/{name}_docs_batch_{batch:03d}.jsonl`.
2. **`chunk_docs.py`** — découpe chaque doc en chunks via `RecursiveCharacterTextSplitter` (tokenizer mpnet, `CHUNK_SIZE=500`, overlap `75`). Génère un `chunk_id` = hash SHA-1 de `source::index::content`. Lit `data/raw/{name}_docs_batch_*.jsonl` et écrit dans `data/chunks/{name}_chunks_batch_*.jsonl` en miroir.
3. **`ingest_weaviate.py`** — calcule les embeddings par lots de `BATCH_SIZE_WEAVIATE`, crée la collection si besoin (nom dérivé de la source via `config.get_collection(name)`) et insère via `insert_many`. UUID déterministe : `uuid3(NAMESPACE_DNS, chunk_id)` → **ré-ingérer est idempotent** (pas de doublons).
4. **`query_weaviate.py`** — script de test *jetable* (hors du pipeline) : exécute une recherche hybride sur une question codée en dur (`QUERY_TEXT`) et affiche les résultats. (Fichier récent, non suivi par git.)

Le logging est configuré par `app/config/logging.yml` (console + fichier rotatif `logs/app.log`), chargé via `app/config/logger_config.py`.

### Chatbot — Streamlit (`chatbot/app.py`) + fusion (`chatbot/fusion.py`)

L'interface Streamlit vit dans `app.py` ; la logique de fusion multi-collections est extraite dans `fusion.py` (module **pur**, sans dépendance Streamlit/Weaviate, importé par `app.py`). À chaque question, l'app :
1. **Traduit en anglais si nécessaire** (`langdetect` + `deep_translator` GoogleTranslator), puis embedde la requête.
2. **Recherche hybride multi-collections** : une requête Weaviate par collection sélectionnée dans la sidebar (`alpha=0.7`, `fusion_type=RELATIVE_SCORE`, `top_k` réglable), puis **fusion min-max** via `fusion.py` (normalisation en [0,1] par collection, tri, tie-break `vector_score`). La pertinence est validée par un seuil `MIN_VECTOR_SCORE=0.45` sur le `vector_score` brut du top-1 fusionné (parsé depuis `explain_score`) : sous le seuil, l'app renvoie un message de repli au lieu d'inventer une réponse.
3. **Génère** avec `ChatMistralAI` un prompt RAG strict : la réponse doit rester dans le contexte fourni, code SQL/Python copié tel quel. La langue de réponse est sélectionnable (FR/EN/DE/NL) via `LANGUAGES`.

Points d'attention :
- `WEAVIATE_HOST = "host.docker.internal"` et les ports sont **codés en dur** (pas via `config.py`).
- La liste `COLLECTIONS` (5 entrées : Snowflake, Databricks, Next.js, TypeScript, Python) et le `COLLECTION_NAME` par défaut (utilisé comme repli de `retrieve_context`) doivent **rester synchronisés** avec les collections réellement ingérées par le pipeline.
- La clé `MISTRAL_API_KEY` vient de la variable d'environnement (voir `chatbot/.env_example`).
- Les `@st.cache_resource` / `@st.cache_data` cachent respectivement le modèle d'embedding (mémoire) et les traductions (1h).

## Infrastructure

`docker-compose.yml` lance Weaviate 1.31 en local avec des **vecteurs fournis par le client** (`DEFAULT_VECTORIZER_MODULE: none`, `ENABLE_MODULES: ""`) : aucun module vectorizer, les vecteurs doivent être passés à l'insertion. Ports : HTTP `9090`, gRPC `50051`. Données persistées dans le volume `weaviate_data`.

Les deux modèles (embedding + tokenizer mpnet) sont **téléchargés depuis HuggingFace au premier run**.

## Commandes

```bash
# Lancer Weaviate local
docker-compose up -d

# Pipeline d'ingestion (dans l'ordre, depuis la racine ; une source par run)
python app/get_docs.py --source typescript        # 1. extraction → data/raw/
python app/chunk_docs.py --source typescript      # 2. chunking → data/chunks/
python app/ingest_weaviate.py --source typescript # 3. embedding + indexation Weaviate
# --source ∈ {snowflake, databricks, nextjs, typescript, python} (défini dans config.SOURCES)

# Test manuel de la recherche hybride
python app/query_weaviate.py

# Chatbot — en développement (dans chatbot/, Weaviate local requis)
streamlit run app.py

# Chatbot — conteneurisé
docker build . -t personal_chatbot --no-cache
docker run -e PORT=7862 -e MISTRAL_API_KEY="<clé>" -p 7862:7862 personal_chatbot
# → http://localhost:7862/

# Tests (fusion + extracteurs ; pytest.ini → tests/)
python -m pytest
```

**pytest** est configuré (`pytest.ini`, `tests/` — fusion multi-collections et extracteurs), dépendance listée dans `requirements-dev.txt` (racine). Pas de linter configuré. `requirements.txt` (racine, ingestion), `requirements-dev.txt` et `chatbot/requirements.txt` (UI) sont indépendants — l'image Docker installe d'abord torch CPU (`torch==2.6.0+cpu`) puis le reste.

## Pièges fréquents

- **Lancer les scripts d'ingestion depuis la racine** : les chemins `./data/...` sont relatifs au répertoire courant.
- **Changer de source de documentation** = éditer la liste **`SOURCES`** de `app/config/config.py` (data-driven, plus de blocs commentés) : chaque source porte son `type`, ses URLs, sa `collection` et son `content_selector`, avec son propre pattern de fichiers (`{name}_docs_batch_*`). Après une modification, relancer `get_docs.py --source <name>` → `chunk_docs.py --source <name>` → `ingest_weaviate.py --source <name>`. Les collections du pipeline doivent rester synchronisées avec `chatbot/app.py` (`COLLECTIONS`).
- **GPU CUDA requis pour l'ingestion** : `config.py` force `EMBEDDING_DEVICE = "cuda:0"`, mais `ingest_weaviate.py` bascule sur CPU si CUDA n'est pas disponible (le chatbot fait pareil). L'ingestion de gros volumes sur CPU est très lente.
- **Ré-ingestion sûre** grâce aux UUID déterministes — utile pour relancer après un changement de config, mais les anciennes entrées restent jusqu'à purge de la collection.
- L'environnement de dev cible Conda + Python 3.12+ (`.vscode/settings.json`).
