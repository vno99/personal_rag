# Personal RAG

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/ui-streamlit-red)](https://streamlit.io/)
[![Vector DB](https://img.shields.io/badge/database-Weaviate-green)](https://weaviate.io/)

Application personnelle de **RAG (Retrieval-Augmented Generation)** : indexe des documentations techniques dans **Weaviate** et les rend interrogables via un chatbot **Streamlit** avec recherche hybride (`alpha=0.7`).

## Fonctionnalités

- **Recherche hybride** (dense `all-mpnet-base-v2` + BM25) fusionnée par collection et triée par `norm_score` (tie-break `vector_score`).
- **5 collections** indexables : Snowflake, Databricks, Next.js, TypeScript, Python (`app/config/config.py`).
- **Chatbot multi-collections** (`chatbot/app.py`) avec sélection manuelle dans la sidebar et seuil de pertinence (`MIN_VECTOR_SCORE=0.45`).
- **Administration pipeline** (`admin/app.py`, Phase B v1) : lancement de runs en sous-processus (`app/runner.py`), suivi temps réel, arrêt, purge, historique borné (`data/status/`).
- **Tests unitaires** (`tests/test_fusion.py`) pour la logique de fusion pure (`chatbot/fusion.py`).

## Stack

- **Pipeline** (`app/`) : extraction (`extractors/`), chunking (`chunk_docs.py`), embedding + indexation (`ingest_weaviate.py`), statut (`status_writer.py`).
- **Chatbot** (`chatbot/`) : Streamlit + `ChatMistralAI` (modèle par défaut `mistral-medium-latest`, surchargeable via `MISTRAL_MODEL`).
- **DB** : Weaviate 1.31 (`docker-compose.yml`), vecteurs fournis côté client (`DEFAULT_VECTORIZER_MODULE: none`).

## Commandes essentielles

```bash
# Lancer Weaviate
docker-compose up -d

# Pipeline (une source = 3 étapes)
python app/get_docs.py --source <snowflake|databricks|nextjs|typescript|python>
python app/chunk_docs.py --source <source>
python app/ingest_weaviate.py --source <source>

# Chatbot (développement)
streamlit run chatbot/app.py

# Administration pipeline
streamlit run admin/app.py

# Tests
python -m pytest
```

## Sources

Définies dans `app/config/config.py` : `sitemap` (Snowflake, Databricks, Next.js), `git` (TypeScript), `archive` (Python 3.14 docs HTML zip).

## Note

Le projet est découpé en trois mondes indépendants : pipeline (`app/`), chatbot (`chatbot/`), administration (`admin/`). Les collections du pipeline et du chatbot doivent rester synchronisées (`COL_COLLECTIONS` dans `chatbot/app.py`).
