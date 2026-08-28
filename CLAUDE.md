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

## Architecture

### Pipeline d'ingestion (`app/`) — un script = une étape, exécutés séquentiellement

Tous les scripts font `import config.config as config` : **`app/config/config.py` est la source unique de vérité** pour la source de docs, les noms de fichiers, la collection Weaviate, la taille des chunks, le modèle d'embedding, etc. Les scripts doivent être lancés **depuis la racine du repo** (`python app/<script>.py`) : les imports `config.*` résolvent `app/`, mais les chemins de données (`./data/...`) sont relatifs.

1. **`get_docs.py`** — extrait les docs depuis un sitemap (par défaut `https://docs.snowflake.com/sitemap.xml`), ne garde que la balise `<article>` de chaque page, et sauvegarde par lots de `BATCH_SIZE_DOCS` dans `data/raw/{pattern}{batch:03d}.jsonl`. Reprend automatiquement au dernier batch existant (création de fichiers reprise).
2. **`chunk_docs.py`** — découpe chaque doc en chunks via `RecursiveCharacterTextSplitter` (tokenizer mpnet, `CHUNK_SIZE=500`, overlap `75`). Génère un `chunk_id` = hash SHA-1 de `source::index::content`. Écrit dans `data/chunks/` en miroir des fichiers raw (le pattern de nom `docs_` → `chunks_`).
3. **`ingest_weaviate.py`** — calcule les embeddings par lots de `BATCH_SIZE_WEAVIATE`, crée la collection si besoin et insère via `insert_many`. UUID déterministe : `uuid3(NAMESPACE_DNS, chunk_id)` → **ré-ingérer est idempotent** (pas de doublons).
4. **`query_weaviate.py`** — script de test *jetable* (hors du pipeline) : exécute une recherche hybride sur une question codée en dur (`QUERY_TEXT`) et affiche les résultats. (Fichier récent, non suivi par git.)

Le logging est configuré par `app/config/logging.yml` (console + fichier rotatif `logs/app.log`), chargé via `app/config/logger_config.py`.

### Chatbot (`chatbot/app.py`) — tout dans un seul fichier

App Streamlit qui à chaque question :
1. **Traduit en anglais si nécessaire** (`langdetect` + `deep_translator` GoogleTranslator), puis embedde la requête.
2. **Recherche hybride** Weaviate (`alpha=0.7`, `fusion_type=RELATIVE_SCORE`, `top_k` réglable). La pertinence est validée par un seuil `MIN_VECTOR_SCORE=0.45` sur le score vectoriel brut (parsé depuis `explain_score`) : si le top-1 est sous le seuil, l'app renvoie un message de repli au lieu d'inventer une réponse.
3. **Génère** avec `ChatMistralAI` un prompt RAG strict : la réponse doit rester dans le contexte fourni, code SQL/Python copié tel quel. La langue de réponse est sélectionnable (FR/EN/DE/NL) via `LANGUAGES`.

Points d'attention :
- `WEAVIATE_HOST = "host.docker.internal"` et les ports sont **codés en dur** (pas via `config.py`).
- La liste `COLLECTIONS` (Snowflake + Databricks) et le `COLLECTION_NAME` par défaut doivent **rester synchronisés** avec les collections réellement ingérées par le pipeline.
- La clé `MISTRAL_API_KEY` vient de la variable d'environnement (voir `chatbot/.env_example`).
- Les `@st.cache_resource` / `@st.cache_data` cachent respectivement le modèle d'embedding (mémoire) et les traductions (1h).

## Infrastructure

`docker-compose.yml` lance Weaviate 1.31 en local avec des **vecteurs fournis par le client** (`DEFAULT_VECTORIZER_MODULE: none`, `ENABLE_MODULES: ""`) : aucun module vectorizer, les vecteurs doivent être passés à l'insertion. Ports : HTTP `9090`, gRPC `50051`. Données persistées dans le volume `weaviate_data`.

Les deux modèles (embedding + tokenizer mpnet) sont **téléchargés depuis HuggingFace au premier run**.

## Commandes

```bash
# Lancer Weaviate local
docker-compose up -d

# Pipeline d'ingestion (dans l'ordre, depuis la racine)
python app/get_docs.py          # 1. extraction sitemap → data/raw/
python app/chunk_docs.py        # 2. chunking → data/chunks/
python app/ingest_weaviate.py   # 3. embedding + indexation Weaviate

# Test manuel de la recherche hybride
python app/query_weaviate.py

# Chatbot — en développement (dans chatbot/, Weaviate local requis)
streamlit run app.py

# Chatbot — conteneurisé
docker build . -t personal_chatbot --no-cache
docker run -e PORT=7862 -e MISTRAL_API_KEY="<clé>" -p 7862:7862 personal_chatbot
# → http://localhost:7862/
```

Pas de tests automatisés ni de linter configuré dans le repo. `requirements.txt` (racine, ingestion) et `chatbot/requirements.txt` (UI) sont indépendants — l'image Docker installe d'abord torch CPU (`torch==2.6.0+cpu`) puis le reste.

## Pièges fréquents

- **Lancer les scripts d'ingestion depuis la racine** : les chemins `./data/...` sont relatifs au répertoire courant.
- **Changer de source de documentation** = éditer `app/config/config.py` : le fichier contient des blocs commentés (LangChain, Databricks) en plus de l'actif (Snowflake). Chaque source a son propre pattern de fichiers ET sa propre collection — penser aussi à la refléter dans `chatbot/app.py` (`COLLECTIONS`).
- **GPU CUDA requis pour l'ingestion** : `config.py` force `EMBEDDING_DEVICE = "cuda:0"`, mais `ingest_weaviate.py` bascule sur CPU si CUDA n'est pas disponible (le chatbot fait pareil). L'ingestion de gros volumes sur CPU est très lente.
- **Ré-ingestion sûre** grâce aux UUID déterministes — utile pour relancer après un changement de config, mais les anciennes entrées restent jusqu'à purge de la collection.
- L'environnement de dev cible Conda + Python 3.12+ (`.vscode/settings.json`).
