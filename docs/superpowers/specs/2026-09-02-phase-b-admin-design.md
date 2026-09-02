# Phase B — App d'administration du pipeline (design)

Date : 2026-09-02. État : validé en brainstorming (décisions utilisateur incluses).

## Contexte et objectif

Le pipeline d'ingestion (`app/get_docs.py`, `app/chunk_docs.py`, `app/ingest_weaviate.py`) ne se pilote
qu'en ligne de commande, une étape à la fois, sans retour visuel sur la progression ni moyen d'arrêter un
run. La Phase B ajoute une **app Streamlit d'administration dédiée** (hors `chatbot/`) qui lance les
ingestions en **sous-processus**, affiche leur **statut temps réel**, permet de les **arrêter** et garde un
**historique** des runs.

Périmètre retenu en brainstorming (itération 1) :

- **Pilotage + statut uniquement.** La *stratégie de fraîcheur* (diff incrémental des pages modifiées via
  `lastmod` / hash git / version d'archive, suppression des pages disparues) est **différée** : elle
  suppose de réécrire le pipeline en incrémental. Hors périmètre : scheduler, purge ciblée.
- **Ingest = chaîne complète** `get_docs → chunk_docs → ingest_weaviate` pour une source, avec **départs
  avancés** (repartir du chunking ou de l'ingestion, sans re-télécharger).
- **Purge = suppression de la collection Weaviate de la source uniquement** (`data/` conservé).
- **Livraison : dossier `admin/` complet** (app.py + requirements.txt + Dockerfile), développement en
  host-side (`streamlit run`), Dockerfile ouvert pour la prod.

## Architecture et fichiers

| Fichier | Rôle |
|---|---|
| `admin/app.py` | UI Streamlit de pilotage (liste des sources, état Weaviate, lancement, suivi, kill, historique). |
| `admin/requirements.txt` | `streamlit`, `weaviate-client` (léger, pas de torch). |
| `admin/Dockerfile` | Image miroir de `chatbot/` (torch CPU + deps pipeline), `CMD` = lancer `admin/app.py`. |
| `app/status_writer.py` | Utilitaire partagé : création et mise à jour du fichier de statut d'un run (écriture atomique). |
| `app/runner.py` | Orchestrateur : exécute une chaîne d'étapes dans **un seul process**, pilote le statut. |
| `app/get_docs.py` | Refactor : `run(source_name, status=None)` + CLI `main()` conservée. |
| `app/chunk_docs.py` | Refactor : idem. |
| `app/ingest_weaviate.py` | Refactor : idem. |
| `app/config/config.py` | Ajout `STATUS_DIR`, `RUNS_HISTORY`. |
| `.gitignore` | Ajout `/data/status/`. |

Invariants :

- Les sous-processus sont lancés avec **`cwd` = racine du repo** (exigence actuelle des chemins relatifs
  `./data/...` et des imports `config.*`).
- **Un run = un process** (PID unique) → le kill est fiable.
- L'instrumentation est **optionnelle** : sans `status`, chaque script garde son comportement et sa sortie
  actuels (CLI et tests inchangés).

## Modèle de données du run

Répertoire : `data/status/` (non versionné). Un run = un fichier nommé `{run_id}_{source}.json`, avec
`run_id` = horodatage local `YYYY-MM-DDTHH-MM-SS` (ex. `2026-09-02T16-20-05_typescript.json`).

Structure (telle que consommée par l'UI) :

```json
{
  "run_id": "2026-09-02T16-20-05",
  "source": "python",
  "operation": "ingest",
  "start_step": "get_docs",
  "steps": ["get_docs", "chunk_docs", "ingest_weaviate"],
  "status": "running",
  "pid": 12345,
  "created_at": "2026-09-02T16:20:05",
  "started_at": "2026-09-02T16:20:06",
  "updated_at": "2026-09-02T16:20:10",
  "finished_at": null,
  "step": "chunk_docs",
  "step_progress": {"done": 3, "total": 5},
  "last_message": "chunk_docs : traitement de chunks_batch_003",
  "error": null
}
```

Transitions de `status` : `running` → `done` | `failed` | `cancelled`.

- `purge` : `operation="purge"`, `steps=["purge"]`, `pid` null (exécuté dans l'app, pas en sous-processus).
- Écriture **atomique** : le JSON est écrit dans un fichier temp puis renommé, pour que l'UI ne lise jamais
  un fichier à moitié écrit.
- `latest.json` : pointeur vers le run le plus récent (mis à jour à chaque transition de statut).
- **Historique borné** : seuls les `RUNS_HISTORY` (10) fichiers de run les plus récents sont conservés ;
  les plus anciens sont supprimés à la création d'un nouveau run.

## Instrumentation des scripts

Chaque script est refactoré pour exposer une fonction réutilisable, la CLI devenant un simple point
d'entrée :

```
def run(source_name: str, status: StatusWriter | None = None) -> None
```

- Sans `status` : comportement strictement identique à aujourd'hui.
- Avec `status` : mise à jour de `step`, `step_progress` et `last_message` à cadence raisonnable, et
  `status.done()` / `status.failed(error)` en fin de parcours (géré par le runner, pas par le script).

Progression rapportée par étape :

| Étape | Unité de `step_progress` | Mesure |
|---|---|---|
| `get_docs` | pages HTML parsées | `total` = nb de fichiers `.html` découverts dans l'archive/le site avant parsing ; `done` incrémenté par page. Via un **callback de progression optionnel** ajouté à `BaseExtractor.extract()`. |
| `chunk_docs` | fichiers batch traités | `total` = nb de fichiers d'entrée (connu avant boucle) ; `done` par fichier terminé. |
| `ingest_weaviate` | chunks insérés | `total` = nb de lignes des fichiers chunks (précompté) ; `done` par lot de `BATCH_SIZE_WEAVIATE` inséré. |

Contrat `BaseExtractor.extract(progress: Callable[[int, int], None] | None = None)` : paramètre optionnel,
défaut `None`. Les extracteurs existants n'en font rien quand il est absent.

## Runner (`app/runner.py`)

Sous-processus lancé par l'admin :

```
python app/runner.py --source python --operation ingest \
    --start-step get_docs --status-file data/status/2026-09-02T16-20-05_python.json
```

Comportement :

1. Charge/initialise le statut : `running`, `pid` (le sien), `started_at`.
2. Détermine la séquence d'étapes à exécuter : pour `operation=ingest`, étapes
   `[get_docs, chunk_docs, ingest_weaviate]` **à partir de `start_step`** ; pour `operation=purge`, le
   run est piloté par l'app (pas de sous-processus), le runner n'est pas appelé (cf. § Opérations).
3. Appelle séquentiellement les `run()` des étapes retenues, chacune recevant un `StatusWriter` ciblant le
   fichier de statut ; chaque script positionne `step` et son `step_progress`.
4. Termine par `done` + `finished_at`.
5. Sur exception non rattrapée : `failed` + `error` (trace courte), puis sortie non nulle.

Départs avancés : `--start-step` vaut `get_docs` | `chunk_docs` | `ingest_weaviate` ; seules les étapes à
partir de celle-ci sont exécutées (les précédentes sont préservées sur disque).

## Opérations exposées

Une **source** (parmi `config.SOURCES`) est toujours sélectionnée. L'UI expose une opération **Ingest**
avec un **point de départ** (sous-ensembles de la chaîne complète), plus l'opération **Purge** :

| Libellé UI | `operation` | `start_step` | Étapes exécutées | Cas d'usage |
|---|---|---|---|---|
| Extraction complète | `ingest` | `get_docs` | `get_docs`, `chunk_docs`, `ingest_weaviate` | Mettre la source à jour depuis zéro. |
| Dès le chunking | `ingest` | `chunk_docs` | `chunk_docs`, `ingest_weaviate` | `data/raw` à jour : re-chunker (taille de chunk modifiée) **puis** ré-ingérer, sans re-télécharger. |
| Dès l'ingestion | `ingest` | `ingest_weaviate` | `ingest_weaviate` | `data/chunks` à jour : ré-embedder/ré-ingérer (embedding modifié), sans re-télécharger ni re-chunker. |
| Purge collection | `purge` | — | `purge` | Supprime la collection Weaviate de la source (direct dans l'app, sans sous-processus). |

Note de périmètre assumée : il n'existe **pas** d'opération « chunk seul » ni « extraction seule » sans
l'étape d'aval — des chunks produits sans ré-ingestion, ou des raw extraits sans chunking, n'ont aucun
effet sur Weaviate et seraient des impasses. Les départs avancés couvrent les vrais besoins (re-chunker /
ré-embedder sans re-télécharger).

## UI Streamlit (`admin/app.py`)

- **En-tête** : état Weaviate (connexion `localhost:9090`, port gRPC `50051` — mêmes valeurs que
  `config.py`) ; liste des 5 sources avec : collection existante ? (oui/non), nombre d'objets, et dernier
  run connu. Bouton « Actualiser ».
- **Lancer un run** : sélecteur de source + opération/point de départ + bouton. Au clic :
  `subprocess.Popen([sys.executable, "app/runner.py", …], cwd=<racine du repo>)`. Le PID est stocké dans le
  fichier de statut et en session.
- **Suivi temps réel** : pendant qu'un run actif existe, l'UI relit son JSON à chaque `st.rerun`
  (rafraîchissement auto à petit intervalle + bouton « Actualiser »), et affiche : `status`, étape courante,
  barre de progression (`step_progress`), `last_message`, durée. Arrêt automatique du rafraîchissement
  quand le run passe en état terminal.
- **Kill** : bouton sur le run actif → termine le process (PID) via `process.terminate()` puis écrit
  `cancelled` (désactivé si le run est déjà terminé).
- **Historique** : les `RUNS_HISTORY` derniers fichiers `data/status/*.json` (tri décroissant), chaque run
  avec pastille de statut, source, opération, timestamps, `last_message`/`error`.
- Weaviate injoignable : message clair, pas de crash. Les opérations de run (sous-processus) restent
  possibles.

## Purge

Exécutée dans l'app (client Weaviate) : `client.collections.delete(nom_collection)` si elle existe.
Confirmation (`st.dialog` ou case à cocher) exigée avant exécution. Les fichiers `data/` et `data/raw_src`
sont conservés. Un run `purge` est tout de même écrit dans l'historique (statut `done`/`failed`).

## Gestion d'erreurs et cas limites

- Étape qui échoue (ex. aucune donnée, réseau) → statut `failed` + `error` ; l'UI affiche `last_message`
  et l'erreur. Les étapes suivantes ne sont pas exécutées.
- Ingest sans fichiers (ex. départ à l'ingestion sans `data/chunks`) → le script lève, run `failed` avec un
  message explicite. Comportement « aucun fichier trouvé » existant préservé pour la CLI.
- Kill d'un run déjà terminé → bouton inactif.
- Lecture d'un statut en cours d'écriture → jamais (écriture atomique).
- Fichier de statut introuvable mais run « actif » en session → l'UI considère le run terminé et nettoie la
  session.

## Tests (pytest)

- `tests/test_status_writer.py` : création, mises à jour (step/step_progress/last_message), transitions
  done/failed/cancelled, écriture atomique (pas de fichier temp résiduel), `latest.json`, pruning à
  `RUNS_HISTORY`.
- `tests/test_runner.py` : enchaînement d'étapes avec des `run()` factices (injection), départ avancé
  (seules les étapes à partir de `start_step` tournent), échec d'une étape → `failed` + `error` et arrêt.
- Régression : les tests existants (extracteurs, chunking, config) passent sans modification ; un test
  vérifie qu'appeler `run(source)` sans `status` équivaut à l'ancien chemin.

## Configuration et documentation

- `app/config/config.py` : `STATUS_DIR = "./data/status"`, `RUNS_HISTORY = 10`.
- `.gitignore` : ajout `/data/status/`.
- `CLAUDE.md` : Phase B passe en « implémentée (v1 pilotage + statut) » ; la stratégie de fraîcheur
  incrémentale et le scheduler sont explicitement marqués **différés** ; commandes admin ajoutées
  (`streamlit run admin/app.py` depuis `admin/`, Dockerfile admin).
- `admin/requirements.txt` : `streamlit`, `weaviate-client`.

## Hors périmètre (différé)

- Stratégie de fraîcheur / diff incrémental (`lastmod` sitemap, hash git, version archive) + suppression des
  pages disparues.
- Scheduler / planification automatique.
- Purge ciblée (par diff de `chunk_id`).
- Build/vérification de l'image Docker admin (Dockerfile fourni, non construit dans cette itération).
