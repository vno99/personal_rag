# Personal RAG

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/ui-streamlit-red)](https://streamlit.io/)
[![Vector DB](https://img.shields.io/badge/database-Weaviate-green)](https://weaviate.io/)

## Présentation
Ce projet est une application de **RAG (Retrieval-Augmented Generation)** avancée. 

Il transforme vos documents statiques en une base de connaissances interactive.  
Grâce à l'utilisation de la recherche hybride (vectorielle + textuelle), l'assistant ne se contente pas de chercher des mots-clés, il **comprend le contexte** des questions posées.

## 🚀 Fonctionnalités Clés

### 🔍 Recherche Hybride (Hybrid Search)
Le coeur du système repose sur une recherche combinant :
*   **Dense Retrieval (Vectoriel) :** Capture la sémantique et le contexte profond grâce aux embeddings.
*   **Sparse Retrieval (BM25/Keyword) :** Assure la précision sur les mots-clés techniques et les noms propres.
*   **Paramétrage Alpha :** Utilisation d'un poids `alpha=0.7` pour équilibrer la sémantique et la précision textuelle.

### 🧠 RAG Avancé
*   **Contextualisation :** Utilisation de LLM pour générer des réponses basées uniquement sur les documents récupérés.

### 🛠️ Stack Technique
*   **Frontend :** [Streamlit](https://streamlit.io/) (Interface utilisateur interactive).
*   **Vector Database :** [Weaviate](httpsh://weaviate.io/) (Stockage et recherche hybride ultra-rapide).
*   **LLM :** Utilisation du model `mistral-large-latest`.
*   **Modèle d'Embeddings :** `sentence-transformers/all-mpnet-base-v2`.

## 🛠️  Architecture Technique

  Le moteur repose sur le pipeline RAG suivant :

  1.  **Ingestion** : Chargement et découpage (chunking) des documents.
  2.  **Embedding** : Transformation du texte en vecteurs numériques.
  3.  **Stockage** : Indexation dans **Weaviate**.
  4.  **Retrieval** : Extraction des chunks les plus pertinents via recherche hybride.
  5.  **Augmentation** : Construction d'un prompt enrichi avec le contexte récupéré.
  6.  **Génération** : Réponse finale générée par le LLM `Mistral`.

## ⚙️ Installation

### Prérequis
* Python 3.12+
* Une instance Weaviate (Locale via Docker ou Cloud).
* Une clé API Mistral.

### Étapes
1. **Cloner le dépôt**
   ```bash
   git clone https://github.com/vno99/personal_rag.git
   cd <votre_dossier>
   ```

2. **Ingestion des données**

   #### Extraction
   Parcours des documents sources pour récupérer le contenu brut. Par défaut, le script extrait les données de la documentation Snowflake via le `sitemap.xml`.
   > **Note :** Pour modifier la source, mettez à jour les paramètres dans `./config/config.py`.
   ```bash
   python ./app/get_docs.py
   ```

   #### Découpage
   Une fois les documents récupérés, ils sont découpés en segments plus petits (chunks) optimisés pour la recherche vectorielle et la fenêtre de contexte du LLM.
   ```bash
   python ./app/chunk_docs.py
   ```

   #### Indexation
   Cette étape transforme les segments de texte en embeddings et les stocke dans la base de données Weaviate.
   ```bash
   python ./app/ingest_weaviate.py
   ```

3. **Lancer Weaviate**
   ```bash
   docker-compose up -d --build
   ```

4. **Déploiement de l'UI**

   #### Construction de l'image
   ```bash
   docker build . -t personal_chatbot --no-cache
   ```
   #### Lancement du conteneur
   ```bash
   docker run \
   -e PORT=7862 \
   -e MISTRAL_API_KEY="VOTRE_CLE_MISTRAL" \
   -p 7862:7862 \
   personal_chatbot
   ```
   
   #### Accès à l'application
   Une fois le conteneur démarré, l'interface est accessible à l'adresse suivante :
   [http://localhost:7862/](http://localhost:7862/)

## 🛠️ Roadmap
- [ ] Utilisation d'un LLM local type `Ollama`.
- [ ] Support des fichiers PDF, Markdown, Docx, html, wiki, ... .
- [ ] Implémentation du Re-ranking (`bge-reranker-large`, `Jina Reranker v2`) pour améliorer la pertinence.
- [ ] Ajout de citations cliquables vers les sources originales.