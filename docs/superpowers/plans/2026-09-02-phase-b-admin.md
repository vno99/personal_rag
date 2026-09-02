# Phase B — App d'administration du pipeline : plan d'implémentation

> **Pour les agents d'exécution :** COMPÉTENCE REQUISE : utiliser `superpowers:subagent-driven-development` (recommandé) ou `superpowers:executing-plans` pour implémenter ce plan tâche par tâche. Étapes en cases à cocher (`- [ ]`).

**Objectif :** Livrer une app Streamlit `admin/` qui lance les runs d'ingestion (get_docs → chunk_docs → ingest_weaviate) en sous-processus unique, en affiche le statut temps réel, permet de les arrêter et garde un historique — avec la purge de collection Weaviate.

**Architecture :** Un utilitaire partagé `app/status_writer.py` écrit des fichiers JSON de statut (atomiques) dans `data/status/` ; les 3 scripts d'ingestion sont refactorés en `run(source, status=None)` (instrumentation optionnelle) ; `app/runner.py` orchestre une chaîne d'étapes dans **un seul process** ; `admin/app.py` (Streamlit) pilote via `subprocess.Popen`, relit les fichiers de statut et propose purge/kill/historique.

**Stack :** Python 3.12 (Conda `rag_3_12`), Streamlit, `weaviate-client` 4.21, pytest. Mêmes conventions que `app/` et `chatbot/`.

**Spec :** `docs/superpowers/specs/2026-09-02-phase-b-admin-design.md`

## Contraintes globales

- Les sous-processus tournent avec `cwd` = racine du repo (chemins `./data/...` relatifs, imports `config.*` résolus via `app/`).
- Un run = un process (PID unique). Instrumentation **optionnelle** : sans `status`, chaque script garde son comportement actuel.
- Noms de fichiers de run : `{run_id}_{source}.json`, `run_id` = `YYYY-MM-DDTHH-MM-SS` (sans `:`).
- Écriture des statuts **atomique** (temp + `os.replace`). Historique borné à `RUNS_HISTORY = 10`.
- `status` ∈ {`running`, `done`, `failed`, `cancelled`} ; `operation` ∈ {`ingest`, `purge`} ; étapes ∈ {`get_docs`, `chunk_docs`, `ingest_weaviate`}.
- Tests : pytest, répertoire `tests/` (conftest ajoute `app/` et `chatbot/` au `sys.path`). Lancer `python -m pytest` depuis la racine.

---

### Tâche 1 : Config + `.gitignore` + `app/status_writer.py` + tests

**Fichiers :**
- Modifier : `app/config/config.py` (après la ligne `RAW_SRC_DIR`)
- Modifier : `.gitignore` (append)
- Créer : `app/status_writer.py`
- Créer : `tests/test_status_writer.py`
- Modifier : `tests/test_config.py`

**Interfaces produites** (consommées par toutes les tâches suivantes) :
- `config.STATUS_DIR = "./data/status"`, `config.RUNS_HISTORY = 10`
- `status_writer.run_id_from_now(now=None) -> str`
- `status_writer.status_path(status_dir, run_id, source) -> Path` (chemin `{run_id}_{source}.json`)
- `status_writer.read_run(path) -> dict | None`
- `status_writer.create_run_file(path, *, run_id, source, operation, start_step, steps, pid=None, status_dir=None) -> dict` (écrit `running`, met à jour `latest.json` et purge si `status_dir` fourni)
- `status_writer.update_run_file(path, **fields) -> dict` (fusionne, force `updated_at`)
- `status_writer.mark_done(path, last_message="terminé")`, `mark_failed(path, error)`, `mark_cancelled(path)`
- `status_writer.list_runs(status_dir) -> list[dict]` (tri `run_id` décroissant, sans `latest.json`)
- `status_writer.latest_run(status_dir) -> dict | None`
- `status_writer.prune_history(status_dir, keep=config.RUNS_HISTORY)`
- `class status_writer.RunReporter(path)` : `.set_step(step)`, `.progress(done, total=None)`, `.message(text)`

- [ ] **Étape 1 : tests d'abord.** Écrire `tests/test_status_writer.py` :

```python
import json
from pathlib import Path

from status_writer import (
    create_run_file, latest_run, list_runs, mark_cancelled, mark_done,
    mark_failed, prune_history, read_run, run_id_from_now, status_path,
    update_run_file,
)


def test_run_id_from_now_has_no_colons():
    rid = run_id_from_now()
    assert ":" not in rid


def test_create_and_read(tmp_path):
    path = status_path(tmp_path, "2026-09-02T16-20-05", "python")
    create_run_file(path, run_id="2026-09-02T16-20-05", source="python", operation="ingest",
                    start_step="chunk_docs", steps=["chunk_docs", "ingest_weaviate"],
                    pid=123, status_dir=tmp_path)
    rec = read_run(path)
    assert rec["status"] == "running"
    assert rec["source"] == "python"
    assert rec["steps"] == ["chunk_docs", "ingest_weaviate"]
    assert rec["pid"] == 123
    assert rec["step"] is None


def test_atomic_write_leaves_no_tmp(tmp_path):
    path = status_path(tmp_path, "r1", "python")
    create_run_file(path, run_id="r1", source="python", operation="ingest",
                    start_step="get_docs", steps=["get_docs"])
    assert not list(tmp_path.glob("*.tmp"))


def test_transitions(tmp_path):
    path = status_path(tmp_path, "r1", "python")
    create_run_file(path, run_id="r1", source="python", operation="ingest",
                    start_step="get_docs", steps=["get_docs"], status_dir=tmp_path)
    mark_done(path)
    rec = read_run(path)
    assert rec["status"] == "done" and rec["finished_at"] is not None
    mark_failed(path, "boom")
    assert read_run(path)["status"] == "failed"
    assert read_run(path)["error"] == "boom"
    mark_cancelled(path)
    rec = read_run(path)
    assert rec["status"] == "cancelled" and rec["error"] is None


def test_update_progress_and_step(tmp_path):
    path = status_path(tmp_path, "r1", "python")
    create_run_file(path, run_id="r1", source="python", operation="ingest",
                    start_step="chunk_docs", steps=["chunk_docs"], status_dir=tmp_path)
    update_run_file(path, step="chunk_docs", step_progress={"done": 2, "total": 5})
    rec = read_run(path)
    assert rec["step"] == "chunk_docs"
    assert rec["step_progress"] == {"done": 2, "total": 5}


def test_latest_and_prune(tmp_path):
    for rid in ["2026-09-02T16-00-00", "2026-09-02T17-00-00", "2026-09-02T18-00-00"]:
        create_run_file(status_path(tmp_path, rid, "python"), run_id=rid, source="python",
                        operation="ingest", start_step="get_docs", steps=["get_docs"],
                        status_dir=tmp_path)
    runs = list_runs(tmp_path)
    assert [r["run_id"] for r in runs] == [
        "2026-09-02T18-00-00", "2026-09-02T17-00-00", "2026-09-02T16-00-00"]
    assert latest_run(tmp_path)["run_id"] == "2026-09-02T18-00-00"
    prune_history(tmp_path, keep=2)
    left = sorted(p.name for p in tmp_path.glob("*.json") if p.name != "latest.json")
    assert left == ["2026-09-02T17-00-00_python.json", "2026-09-02T18-00-00_python.json"]
    assert (tmp_path / "latest.json").exists()
```

Écrire aussi dans `tests/test_config.py` (append) :

```python
def test_status_constants():
    assert config.STATUS_DIR == "./data/status"
    assert config.RUNS_HISTORY == 10
```

- [ ] **Étape 2 : vérifier l'échec.**

Run : `python -m pytest tests/test_config.py::test_status_constants tests/test_status_writer.py -q`
Attendu : échec à l'import (`ModuleNotFoundError: status_writer`) / assertion `config.STATUS_DIR`.

- [ ] **Étape 3 : implémenter.** Ajouter dans `app/config/config.py` après `RAW_SRC_DIR = "./data/raw_src"` :

```python
STATUS_DIR = "./data/status"
RUNS_HISTORY = 10
```

Append à `.gitignore` (nouvelle ligne à la fin) :

```
/data/status/
```

Créer `app/status_writer.py` :

```python
"""Gestion du statut des runs d'ingestion (Phase B).

Écrit un fichier JSON par run dans data/status/, de façon atomique, plus un
pointeur latest.json. Utilisé par le runner (sous-processus) et l'app
d'administration (UI + purge).
"""
import json
import os
from datetime import datetime
from pathlib import Path

import config.config as config


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def run_id_from_now(now: datetime | None = None) -> str:
    """run_id lisible en nom de fichier : 2026-09-02T16-20-05."""
    base = (now or datetime.now()).isoformat(timespec="seconds")
    return base.replace(":", "-")


def status_path(status_dir, run_id: str, source: str) -> Path:
    return Path(status_dir) / f"{run_id}_{source}.json"


def read_run(path) -> dict | None:
    path = Path(path)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def create_run_file(path, *, run_id, source, operation, start_step, steps,
                    pid=None, status_dir=None) -> dict:
    path = Path(path)
    now = _now_iso()
    record = {
        "run_id": run_id,
        "source": source,
        "operation": operation,
        "start_step": start_step,
        "steps": list(steps),
        "status": "running",
        "pid": pid,
        "created_at": now,
        "started_at": now,
        "updated_at": now,
        "finished_at": None,
        "step": None,
        "step_progress": {"done": 0, "total": None},
        "last_message": "démarrage",
        "error": None,
    }
    _atomic_write(path, record)
    if status_dir is not None:
        _set_latest(status_dir, path)
        prune_history(status_dir)
    return record


def update_run_file(path, **fields) -> dict:
    path = Path(path)
    record = read_run(path) or {}
    for key, value in fields.items():
        record[key] = value
    record["updated_at"] = _now_iso()
    _atomic_write(path, record)
    return record


def mark_done(path, last_message="terminé") -> dict:
    return update_run_file(path, status="done", finished_at=_now_iso(), last_message=last_message)


def mark_failed(path, error) -> dict:
    return update_run_file(path, status="failed", finished_at=_now_iso(), error=str(error))


def mark_cancelled(path) -> dict:
    return update_run_file(path, status="cancelled", finished_at=_now_iso(),
                           error=None, last_message="annulé")


def _set_latest(status_dir, path: Path) -> None:
    info = read_run(path) or {}
    latest_path = Path(status_dir) / "latest.json"
    _atomic_write(latest_path, {"file": path.name, "run_id": info.get("run_id"),
                                "updated_at": _now_iso()})


def latest_run(status_dir) -> dict | None:
    latest_path = Path(status_dir) / "latest.json"
    if not latest_path.exists():
        return None
    info = json.loads(latest_path.read_text(encoding="utf-8"))
    return read_run(Path(status_dir) / info["file"])


def list_runs(status_dir) -> list[dict]:
    status_dir = Path(status_dir)
    if not status_dir.exists():
        return []
    records = []
    for f in status_dir.glob("*.json"):
        if f.name == "latest.json":
            continue
        rec = read_run(f)
        if rec:
            records.append(rec)
    records.sort(key=lambda r: r.get("run_id", ""), reverse=True)
    return records


def prune_history(status_dir, keep: int = config.RUNS_HISTORY) -> None:
    status_dir = Path(status_dir)
    if not status_dir.exists():
        return
    files = sorted(f for f in status_dir.glob("*.json") if f.name != "latest.json")
    for f in files[:-keep] if keep else files:
        f.unlink(missing_ok=True)


class RunReporter:
    """Rapporteur de progression d'une étape (utilisé par runner et scripts)."""

    def __init__(self, path):
        self.path = Path(path)

    def set_step(self, step: str) -> None:
        update_run_file(self.path, step=step, step_progress={"done": 0, "total": None})

    def progress(self, done: int, total: int | None = None) -> None:
        update_run_file(self.path, step_progress={"done": done, "total": total})

    def message(self, text: str) -> None:
        update_run_file(self.path, last_message=text)
```

- [ ] **Étape 4 : vérifier le passage.**

Run : `python -m pytest tests/test_config.py tests/test_status_writer.py -q`
Attendu : PASS.

- [ ] **Étape 5 : commit.**

```bash
git add app/config/config.py app/status_writer.py .gitignore tests/test_status_writer.py tests/test_config.py
git commit -m "feat(admin): statut des runs (status_writer) + config STATUS_DIR"
```

---

### Tâche 2 : Progress optionnel dans les extracteurs (base + archive + git + sitemap)

**Fichiers :**
- Modifier : `app/extractors/base.py`
- Modifier : `app/extractors/archive.py`
- Modifier : `app/extractors/git.py`
- Modifier : `app/extractors/sitemap.py`
- Modifier : `tests/test_archive_extractor.py`, `tests/test_sitemap_extractor.py`

**Interfaces produites** : `BaseExtractor.extract(self, progress: Callable[[int, int | None], None] | None = None) -> list[Path]`, appelé par les 3 sous-classes. `progress(done, total)` avec `done` = pages/documents déjà parcourus, `total` = nombre connu (`int`) pour archive/git, `None` pour sitemap (inconnu d'avance). Paramètre optionnel → tous les appels existants (`extract()`) restent valides.

- [ ] **Étape 1 : tests d'abord.** Ajouter dans `tests/test_archive_extractor.py` :

```python
def test_archive_extractor_reports_progress(tmp_path, monkeypatch):
    archive = make_local_zip(tmp_path)

    def fake_urlretrieve(url: str, dest):
        shutil.copyfile(archive, dest)

    monkeypatch.setattr("urllib.request.urlretrieve", fake_urlretrieve)
    source = {
        "name": "python", "type": "archive",
        "archive_url": f"https://docs.python.org/3.14/archives/{archive.name}",
        "collection": "PythonDocs", "content_selector": "[role='main']",
    }
    calls = []
    extractor = ArchiveExtractor(source, tmp_path / "raw", batch_size=500, cache_dir=tmp_path / "src")
    extractor.extract(progress=lambda done, total: calls.append((done, total)))
    assert calls == [(1, 2), (2, 2)]
```

Ajouter dans `tests/test_sitemap_extractor.py` :

```python
def test_sitemap_extractor_reports_progress(tmp_path):
    batches = [
        [FakeDoc("A", "https://x.com/a", "a", None), FakeDoc("B", "https://x.com/b", "b", None)],
        [],
    ]
    n = {"i": 0}

    def loader_factory(**kwargs):
        docs = batches[n["i"]]
        n["i"] += 1
        return FakeLoader(docs)

    source = {
        "name": "nextjs", "type": "sitemap",
        "sitemap_url": "https://nextjs.org/sitemap.xml",
        "filter_urls": [r"https://nextjs\.org/docs/.*"],
        "collection": "NextJSDocs", "content_selector": "article",
    }
    calls = []
    extractor = SitemapExtractor(source, tmp_path, batch_size=500, loader_factory=loader_factory)
    extractor.extract(progress=lambda done, total: calls.append((done, total)))
    assert calls == [(2, None)]
```

- [ ] **Étape 2 : vérifier l'échec.**

Run : `python -m pytest tests/test_archive_extractor.py::test_archive_extractor_reports_progress tests/test_sitemap_extractor.py::test_sitemap_extractor_reports_progress -q`
Attendu : FAIL (`TypeError` : `extract() got an unexpected keyword argument 'progress'`).

- [ ] **Étape 3 : implémenter.** Dans `app/extractors/base.py` : importer `Callable`, définir l'alias, changer la signature abstraite et la docstring :

```python
from typing import Callable
...
ProgressCallback = Callable[[int, int | None], None]
...
    @abstractmethod
    def extract(self, progress: ProgressCallback | None = None) -> list[Path]:
        """Extrait les documents et écrit les fichiers JSONL bruts.

        Args:
            progress: callback optionnel appelé avec (done, total) au fil de
                l'extraction ; `total` vaut None quand il est inconnu d'avance.

        Returns:
            list[Path]: Les chemins des fichiers batch écrits.
        """
        raise NotImplementedError
```

Dans `app/extractors/archive.py`, remplacer la boucle de parsing pour rapporter la progression (en-tête de méthode et boucle) :

```python
    def extract(self, progress=None) -> list[Path]:
        archive = self._download()
        root = self._extract_zip(archive)
        base_url = self._base_url()

        written: list[Path] = []
        batch: list[dict] = []
        batch_num = 0
        html_files = sorted(root.rglob("*.html"))
        total = len(html_files)

        for done, html_file in enumerate(html_files, start=1):
            if progress is not None:
                progress(done, total)
            rel = html_file.relative_to(root).as_posix()
            soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "lxml")
            content = extract_from_soup(soup, self.selector)
            if not content.strip():
                continue
            record = {
                "source": f"{base_url}/{rel}",
                "loc": rel,
                "lastmod": None,
                "content": content,
            }
            batch.append(record)
            if len(batch) >= self.batch_size:
                written.append(self._save_batch(batch, batch_num))
                batch = []
                batch_num += 1

        if batch:
            written.append(self._save_batch(batch, batch_num))
        return written
```

Dans `app/extractors/git.py`, remplacer la signature et la boucle d'écriture :

```python
    def extract(self, progress=None) -> list[Path]:
        repo = self._clone_or_fetch()
        docs_root = repo / self.docs_path
        md_files = sorted(docs_root.rglob("*.md"))
        total = len(md_files)

        written: list[Path] = []
        batch: list[dict] = []
        batch_num = 0

        for done, md_file in enumerate(md_files, start=1):
            if progress is not None:
                progress(done, total)
            rel_path = md_file.relative_to(repo)
            content = md_file.read_text(encoding="utf-8")
            record = {
                "source": self._blob_url(rel_path),
                "loc": rel_path.as_posix(),
                "lastmod": self._last_modified(rel_path),
                "content": content,
            }
            batch.append(record)
            if len(batch) >= self.batch_size:
                written.append(self._save_batch(batch, batch_num))
                batch = []
                batch_num += 1

        if batch:
            written.append(self._save_batch(batch, batch_num))
        return written
```

Dans `app/extractors/sitemap.py`, remplacer la signature et la boucle de la méthode `extract()` :

```python
    def extract(self, progress=None) -> list[Path]:
        written: list[Path] = []
        blocknum = self._find_next_batch_num()
        done = 0

        while True:
            loader = self._make_loader(blocknum)
            try:
                docs = loader.load()
            except ValueError as e:
                if "does not contain enough blocks" in str(e):
                    break
                raise

            if not docs:
                break

            records = [
                {
                    "source": doc.metadata.get("source"),
                    "loc": doc.metadata.get("loc"),
                    "lastmod": doc.metadata.get("lastmod"),
                    "content": doc.page_content,
                }
                for doc in docs
            ]
            written.append(self._save_batch(records, blocknum))
            done += len(records)
            if progress is not None:
                progress(done, None)
            blocknum += 1

        return written
```

- [ ] **Étape 4 : vérifier le passage.**

Run : `python -m pytest tests/test_archive_extractor.py tests/test_sitemap_extractor.py -q`
Attendu : PASS (nouveaux tests + existants, y compris le git s'il existe, inchangé).

- [ ] **Étape 5 : commit.**

```bash
git add app/extractors/base.py app/extractors/archive.py app/extractors/git.py app/extractors/sitemap.py tests/test_archive_extractor.py tests/test_sitemap_extractor.py
git commit -m "feat(admin): extracteurs exposent une progression optionnelle"
```

---

### Tâche 3 : Refactor des scripts en `run(source, status=None)` + reporting

**Fichiers :**
- Modifier : `app/get_docs.py`
- Modifier : `app/chunk_docs.py`
- Modifier : `app/ingest_weaviate.py`
- Modifier : `tests/test_ingest_helpers.py`

**Interfaces produites** (consommées par le runner, tâche 4) :
- `get_docs.run(source_name: str, status=None) -> None`
- `chunk_docs.run(source_name: str, status=None) -> None`
- `ingest_weaviate.run(source_name: str, status=None) -> None`
- `ingest_weaviate.ingest_file(weaviate_collection, embeddings, file_path, progress: Callable[[int], None] | None = None) -> None`
- Convention : `status` (si non-None) est un objet à `.progress(done, total=None)` et `.message(text)` (le `RunReporter` de la tâche 1). Les scripts ne positionnent ni `status` terminal ni `step` (le runner s'en charge).

- [ ] **Étape 1 : tests d'abord (ingest_file progress).** Ajouter dans `tests/test_ingest_helpers.py` :

```python
from types import SimpleNamespace

from ingest_weaviate import ingest_file


class _FakeData:
    def __init__(self):
        self.inserted = []

    def insert_many(self, objects):
        self.inserted.append(len(objects))
        return SimpleNamespace(errors=None)


class _FakeColl:
    def __init__(self):
        self.data = _FakeData()


class _FakeEmb:
    def embed_documents(self, texts):
        return [[0.1, 0.2] for _ in texts]


def test_ingest_file_reports_progress_per_batch(tmp_path):
    lines = "\n".join(f'{{"chunk_id": "c{i}", "content": "contenu {i}"}}' for i in range(250))
    (tmp_path / "chunks.jsonl").write_text(lines, encoding="utf-8")
    coll = _FakeColl()
    calls = []
    ingest_file(coll, _FakeEmb(), tmp_path / "chunks.jsonl", progress=lambda n: calls.append(n))
    assert calls == [100, 100, 50]
    assert coll.data.inserted == [100, 100, 50]
```

- [ ] **Étape 2 : vérifier l'échec.**

Run : `python -m pytest tests/test_ingest_helpers.py::test_ingest_file_reports_progress_per_batch -q`
Attendu : FAIL (`TypeError` : `ingest_file() got an unexpected keyword argument 'progress'`).

- [ ] **Étape 3 : implémenter.**

`app/get_docs.py` : remplacer la fonction `main()` et ajouter `run()` ; garder le `if __name__ == "__main__"` :

```python
def run(source_name: str, status=None) -> None:
    source = config.get_source(source_name)
    extractor_cls = EXTRACTORS[source["type"]]
    extractor = extractor_cls(
        source,
        raw_dir=Path(config.RAW_DATA_DIR),
        batch_size=config.BATCH_SIZE_DOCS,
    )

    logger.info(f"Début de l'extraction de la source '{source_name}' ({source['type']})")

    def progress(done: int, total: int | None) -> None:
        if status is not None:
            status.progress(done, total)

    written = extractor.extract(progress=progress)
    logger.info(f"Terminé : {len(written)} fichier(s) batch écrit(s) pour '{source_name}'")


def main():
    parser = argparse.ArgumentParser(description="Extraction des docs d'une source")
    parser.add_argument(
        "--source",
        required=True,
        choices=[source["name"] for source in config.SOURCES],
        help="Nom de la source à extraire",
    )
    args = parser.parse_args()
    run(args.source)


if __name__ == "__main__":
    main()
```

`app/chunk_docs.py` : remplacer la fonction `main()` par `run()` + `main()` (le reste du fichier — helpers, tokenizer, splitter — inchangé) :

```python
def run(source_name: str, status=None) -> None:
    docs_pattern = config.docs_pattern(source_name)
    chunks_pattern = config.chunks_pattern(source_name)

    input_files = sorted(RAW_DIR.glob(f"{docs_pattern}*.{config.JSONL_EXT}"))
    logger.info(f"input_files : {input_files}")

    total_files = len(input_files)
    total_chunks = 0
    done_files = 0

    for input_file in input_files:
        output_file = CHUNKS_DIR / input_file.name.replace(docs_pattern, chunks_pattern)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        file_chunks = 0
        with input_file.open("r", encoding="utf-8") as fin:
            with output_file.open("w", encoding="utf-8") as fout:
                for line_num, line in enumerate(fin, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON invalide dans {input_file.name}, ligne {line_num}: {e}")
                        continue

                    chunks = chunk_one_record(record)
                    for chunk in chunks:
                        fout.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                    file_chunks += len(chunks)

        done_files += 1
        total_chunks += file_chunks
        logger.info(f"Terminé {input_file.name} : {file_chunks} chunks")
        if status is not None:
            status.progress(done_files, total_files)
            status.message(f"Terminé {input_file.name}: {file_chunks} chunks ({total_chunks} au total)")

    logger.info(f"Terminé. {total_chunks} chunks au total")


def main():
    parser = argparse.ArgumentParser(description="Découpe les docs brutes en chunks")
    parser.add_argument(
        "--source",
        required=True,
        choices=[source["name"] for source in config.SOURCES],
        help="Nom de la source à chunker",
    )
    args = parser.parse_args()
    run(args.source)


if __name__ == "__main__":
    main()
```

`app/ingest_weaviate.py` :
1. `ingest_file(weaviate_collection, embeddings, file_path, progress=None)` — ajouter le paramètre et appeler `progress` en tête de chaque batch :

```python
def ingest_file(weaviate_collection, embeddings, file_path: Path, progress=None):
    """... (docstring existante, + paramètre progress optionnel) ..."""
    logger.info(f"Ingestion de {file_path.name}...")

    total = 0
    failed = 0

    records = read_jsonl_file(file_path)

    for batch_num, records_batch in enumerate(batch_iterable(records, BATCH_SIZE_WEAVIATE), start=1):
        if progress is not None:
            progress(len(records_batch))

        texts = [record.get("content", "") for record in records_batch]
        # ... (le reste de la boucle existante est inchangé) ...
```

2. Remplacer `main()` par `run()` + `main()` :

```python
def run(source_name: str, status=None) -> None:
    collection_name = config.get_collection(source_name)
    chunks_pattern = config.chunks_pattern(source_name)

    input_files = sorted(CHUNKS_DATA_DIR.glob(f"{chunks_pattern}*.{config.JSONL_EXT}"))

    if not input_files:
        logger.info(f"Aucun fichier {chunks_pattern}*.{config.JSONL_EXT} trouvé dans {CHUNKS_DATA_DIR}")
        return

    logger.info(f"{len(input_files)} fichiers trouvés dans {CHUNKS_DATA_DIR}")
    total = sum(1 for f in input_files for _ in read_jsonl_file(f))
    logger.info(f"{total} chunks à ingérer")

    if status is not None:
        status.progress(0, total)
        status.message(f"{total} chunks à ingérer")

    embeddings = get_embeddings()
    client = connect_client()
    processed = 0

    def on_progress(n: int) -> None:
        nonlocal processed
        processed += n
        if status is not None:
            status.progress(processed, total)

    try:
        weaviate_collection = get_collection(client, collection_name)
        for file_path in input_files:
            ingest_file(weaviate_collection, embeddings, file_path, progress=on_progress)
        logger.info(f"Ingestion Weaviate terminée pour '{source_name}'.")
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description="Embedding + indexation Weaviate d'une source")
    parser.add_argument(
        "--source",
        required=True,
        choices=[source["name"] for source in config.SOURCES],
        help="Nom de la source à ingérer",
    )
    args = parser.parse_args()
    run(args.source)


if __name__ == "__main__":
    main()
```

- [ ] **Étape 4 : vérifier le passage + régression.**

Run : `python -m pytest -q`
Attendu : PASS (tous les tests existants + le nouveau). La CLI des 3 scripts n'est pas modifiée dans son comportement (`python app/<script>.py --source X` appelle `run(X)` sans `status`).

- [ ] **Étape 5 : commit.**

```bash
git add app/get_docs.py app/chunk_docs.py app/ingest_weaviate.py tests/test_ingest_helpers.py
git commit -m "feat(admin): scripts d'ingestion exposent run(source, status)"
```

---

### Tâche 4 : `app/runner.py` + tests

**Fichiers :**
- Créer : `app/runner.py`
- Créer : `tests/test_runner.py`

**Interfaces produites** (consommées par l'admin, tâche 5) :
- `runner.compute_steps(operation: str, start_step: str) -> list[str]`
- `runner.execute_run(*, run_id, source, operation, start_step, status_dir, run_funcs) -> None`
- `runner.main(argv=None) -> int` (CLI : `--source`, `--run-id`, `--operation` (ingest), `--start-step`)
- `_real_run_funcs() -> dict[str, Callable]` (résout `get_docs/chunk_docs/ingest_weaviate` vers les `run()` de la tâche 3)

- [ ] **Étape 1 : tests d'abord.** Créer `tests/test_runner.py` :

```python
import pytest

from runner import compute_steps, execute_run
from status_writer import read_run, status_path


def test_compute_steps_full():
    assert compute_steps("ingest", "get_docs") == ["get_docs", "chunk_docs", "ingest_weaviate"]


def test_compute_steps_advanced_starts():
    assert compute_steps("ingest", "chunk_docs") == ["chunk_docs", "ingest_weaviate"]
    assert compute_steps("ingest", "ingest_weaviate") == ["ingest_weaviate"]


def test_compute_steps_rejects_purge():
    with pytest.raises(ValueError):
        compute_steps("purge", "get_docs")


def test_execute_run_success_writes_done(tmp_path):
    calls = []

    def make(step):
        def run(source, status):
            calls.append(step)
            status.progress(1, 1)
        return run

    funcs = {"get_docs": make("get_docs"), "chunk_docs": make("chunk_docs"),
             "ingest_weaviate": make("ingest_weaviate")}
    execute_run(run_id="2026-09-02T10-00-00", source="python", operation="ingest",
                start_step="chunk_docs", status_dir=tmp_path, run_funcs=funcs)
    assert calls == ["chunk_docs", "ingest_weaviate"]
    rec = read_run(status_path(tmp_path, "2026-09-02T10-00-00", "python"))
    assert rec["status"] == "done"
    assert rec["step_progress"] == {"done": 1, "total": 1}
    assert rec["pid"] is not None


def test_execute_run_failure_marks_failed_and_stops(tmp_path):
    def boom(source, status):
        raise RuntimeError("explose")

    funcs = {"get_docs": boom, "chunk_docs": lambda s, st: None,
             "ingest_weaviate": lambda s, st: None}
    with pytest.raises(RuntimeError):
        execute_run(run_id="2026-09-02T10-00-01", source="python", operation="ingest",
                    start_step="get_docs", status_dir=tmp_path, run_funcs=funcs)
    rec = read_run(status_path(tmp_path, "2026-09-02T10-00-01", "python"))
    assert rec["status"] == "failed"
    assert "explose" in rec["error"]
```

- [ ] **Étape 2 : vérifier l'échec.**

Run : `python -m pytest tests/test_runner.py -q`
Attendu : FAIL (`ModuleNotFoundError: runner`).

- [ ] **Étape 3 : implémenter.** Créer `app/runner.py` :

```python
"""Orchestrateur de run d'ingestion (Phase B).

Lancé en sous-processus par l'app d'administration. Un run = un process :
il exécute séquentiellement les run() des étapes demandées (une source),
en écrivant sa progression dans data/status/{run_id}_{source}.json.
"""
import argparse
import os
import sys
from pathlib import Path

import config.config as config
from status_writer import RunReporter, create_run_file, mark_done, mark_failed, status_path

FULL_STEPS = ["get_docs", "chunk_docs", "ingest_weaviate"]


def compute_steps(operation: str, start_step: str) -> list[str]:
    """Étapes d'un run d'ingestion à partir de l'opération et du point de départ."""
    if operation != "ingest":
        raise ValueError(f"opération non gérée par le runner: {operation!r} (purge = app)")
    try:
        index = FULL_STEPS.index(start_step)
    except ValueError:
        raise ValueError(f"start_step inconnu: {start_step!r} (attendu: {FULL_STEPS})") from None
    return FULL_STEPS[index:]


def execute_run(*, run_id, source, operation, start_step, status_dir, run_funcs) -> None:
    """Exécute un run complet. Soulève en cas d'échec (après marquage failed)."""
    steps = compute_steps(operation, start_step)
    path = status_path(status_dir, run_id, source)
    create_run_file(path, run_id=run_id, source=source, operation=operation,
                    start_step=start_step, steps=steps, pid=os.getpid(), status_dir=status_dir)
    reporter = RunReporter(path)
    try:
        for step in steps:
            reporter.set_step(step)
            run_funcs[step](source, reporter)
        mark_done(path)
    except Exception as exc:
        mark_failed(path, f"{type(exc).__name__}: {exc}")
        raise


def _real_run_funcs():
    from get_docs import run as run_get_docs
    from chunk_docs import run as run_chunk
    from ingest_weaviate import run as run_ingest
    return {"get_docs": run_get_docs, "chunk_docs": run_chunk, "ingest_weaviate": run_ingest}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Exécute un run d'ingestion pour une source.")
    parser.add_argument("--source", required=True, choices=[s["name"] for s in config.SOURCES],
                        help="Source à ingérer")
    parser.add_argument("--run-id", required=True,
                        help="Identifiant du run, ex. 2026-09-02T16-20-05")
    parser.add_argument("--operation", default="ingest", choices=["ingest"])
    parser.add_argument("--start-step", default="get_docs", choices=FULL_STEPS)
    args = parser.parse_args(argv)
    try:
        execute_run(run_id=args.run_id, source=args.source, operation=args.operation,
                    start_step=args.start_step, status_dir=Path(config.STATUS_DIR),
                    run_funcs=_real_run_funcs())
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Étape 4 : vérifier le passage.**

Run : `python -m pytest tests/test_runner.py -q`
Attendu : PASS.

- [ ] **Étape 5 : smoke test CLI réel (optionnel mais conseillé).** Depuis la racine, lancer une ré-ingestion rapide de TypeScript (chunks existants, idempotent par UUID déterministe) et vérifier le fichier de statut :

```bash
python app/runner.py --source typescript --run-id smoke-$(date +%Y%m%dT%H%M%S) --operation ingest --start-step ingest_weaviate
ls data/status/ | tail -3
python -c "import json,glob; print(json.load(open(sorted(glob.glob('data/status/*.json'))[-1]))['status'])"
```

- [ ] **Étape 6 : commit.**

```bash
git add app/runner.py tests/test_runner.py
git commit -m "feat(admin): runner orchestrant un run d'ingestion en un process"
```

---

### Tâche 5 : App Streamlit `admin/` (app.py + requirements.txt + Dockerfile)

**Fichiers :**
- Créer : `admin/app.py`
- Créer : `admin/requirements.txt`
- Créer : `admin/Dockerfile`

**Interfaces consommées :** `config.SOURCES`, `config.get_collection`, `config.WEAVIATE_HOST/PORT/GRPC_PORT`, `config.STATUS_DIR`, `status_path`, `create_run_file`, `read_run`, `list_runs`, `update_run_file`, `mark_done`, `mark_failed`, `mark_cancelled`, `RunReporter` (tâches 1–4). CLI runner : `[sys.executable, "app/runner.py", "--source", …, "--run-id", …, "--operation", "ingest", "--start-step", …]` avec `cwd=ROOT`.

Pas de test unitaire (UI) ; la logique pilotée (statuts, runner) est couverte par les tâches 1–4. **Validation manuelle** : tâche 6.

- [ ] **Étape 1 : écrire `admin/requirements.txt`**

```
streamlit
weaviate-client==4.21.0
```

- [ ] **Étape 2 : écrire `admin/Dockerfile`** (miroir de `chatbot/Dockerfile` ; git requis pour l'extracteur git)

```dockerfile
FROM python:3.12-slim

WORKDIR /home/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    nano curl unzip git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir torch==2.6.0+cpu --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY admin/requirements.txt admin/requirements.txt
RUN pip install --no-cache-dir -r admin/requirements.txt

COPY . .

CMD streamlit run --server.port $PORT admin/app.py
```

- [ ] **Étape 3 : écrire `admin/app.py`** (intégralité) :

```python
"""App d'administration du pipeline RAG (Phase B).

Lance les runs d'ingestion en sous-processus (app/runner.py), affiche leur
statut temps réel (data/status/*.json), permet de les arrêter, purge une
collection Weaviate et garde un historique borné.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "app"))

import config.config as config  # noqa: E402
from status_writer import (  # noqa: E402
    create_run_file, list_runs, mark_cancelled, mark_done, mark_failed,
    read_run, run_id_from_now, status_path, update_run_file,
)

STATUS_DIR = Path(config.STATUS_DIR)

START_STEPS = {
    "Extraction complète": "get_docs",
    "Dès le chunking (raw existants)": "chunk_docs",
    "Dès l'ingestion (chunks existants)": "ingest_weaviate",
}
TERMINAL = {"done", "failed", "cancelled"}

SOURCE_CHOICES = [s["name"] for s in config.SOURCES]


def weaviate_ready() -> bool:
    try:
        connect_client().close()
        return True
    except Exception:
        return False


@st.cache_resource
def connect_client():
    import weaviate
    return weaviate.connect_to_local(
        host=config.WEAVIATE_HOST, port=config.WEAVIATE_PORT,
        grpc_port=config.WEAVIATE_GRPC_PORT,
    )


def collection_counts() -> dict[str, int | None]:
    """{nom_source: nb_objets | None si collection absente}."""
    counts = {}
    try:
        client = connect_client()
        existing = set(client.collections.list_all())
    except Exception:
        return {}
    for src in config.SOURCES:
        name = src["collection"]
        try:
            if name in existing:
                counts[src["name"]] = client.collections.get(name).aggregate.over_all(
                    total_count=True).total_count
            else:
                counts[src["name"]] = None
        except Exception:
            counts[src["name"]] = None
    return counts


def launch_ingest(source: str, label: str) -> None:
    run_id = run_id_from_now()
    path = status_path(STATUS_DIR, run_id, source)
    cmd = [
        sys.executable, "app/runner.py",
        "--source", source, "--run-id", run_id,
        "--operation", "ingest", "--start-step", START_STEPS[label],
    ]
    try:
        subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:  # ex. python introuvable : on trace un run failed
        STATUS_DIR.mkdir(parents=True, exist_ok=True)
        create_run_file(path, run_id=run_id, source=source, operation="ingest",
                        start_step=START_STEPS[label],
                        steps=[START_STEPS[label]], status_dir=STATUS_DIR)
        mark_failed(path, f"impossible de lancer le runner: {exc}")
    st.session_state["active"] = {"run_id": run_id, "source": source,
                                  "label": label, "path": str(path)}


def purge_collection(source: str) -> None:
    collection = config.get_collection(source)
    run_id = run_id_from_now()
    path = status_path(STATUS_DIR, run_id, source)
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    create_run_file(path, run_id=run_id, source=source, operation="purge",
                    start_step="purge", steps=["purge"], status_dir=STATUS_DIR)
    try:
        client = connect_client()
        existing = set(client.collections.list_all())
        if collection in existing:
            client.collections.delete(collection)
        mark_done(path, last_message=f"Collection {collection} supprimée")
    except Exception as exc:
        mark_failed(path, str(exc))
    st.session_state.pop("active", None)


def kill_active(entry: dict) -> None:
    rec = read_run(Path(entry["path"]))
    pid = (rec or {}).get("pid")
    if pid:
        try:
            os.kill(pid, 9)  # Windows : TerminateProcess ; Unix : SIGKILL
        except ProcessLookupError:
            pass
        except OSError:
            pass
    mark_cancelled(entry["path"])
    st.session_state.pop("active", None)


def render_run(rec: dict) -> None:
    st.markdown(f"**Statut :** `{rec.get('status')}` — étape : `{rec.get('step') or '—'}`")
    prog = rec.get("step_progress") or {}
    done, total = prog.get("done", 0), prog.get("total")
    if total:
        st.progress(min(done / total, 1.0), text=f"{done}/{total}")
    st.write(f"PID : `{rec.get('pid')}` — {rec.get('last_message') or ''}")
    if rec.get("error"):
        st.error(rec["error"])


def render_history() -> None:
    runs = list_runs(STATUS_DIR)
    if not runs:
        st.info("Aucun run pour l'instant.")
        return
    for r in runs:
        status = r.get("status", "?")
        emoji = {"done": "✅", "failed": "❌", "running": "🔄",
                 "cancelled": "⏹️"}.get(status, "❔")
        with st.expander(f"{emoji} {r['run_id']} — {r['source']} ({r['operation']})"):
            st.json(r)


def main() -> None:
    st.set_page_config(page_title="Admin RAG", page_icon="⚙️", layout="wide")
    st.title("⚙️ Administration du pipeline RAG")

    ok = weaviate_ready()
    if not ok:
        st.warning(f"Weaviate injoignable sur {config.WEAVIATE_HOST}:{config.WEAVIATE_PORT} — "
                   "les collections affichées seront vides (les runs restent possibles).")

    counts = collection_counts()

    with st.container(border=True):
        st.subheader("Sources")
        data = [
            {
                "source": s["name"],
                "collection": s["collection"],
                "type": s["type"],
                "objets": counts.get(s["name"]) if counts else "—",
            }
            for s in config.SOURCES
        ]
        st.dataframe(data, use_container_width=True)

    with st.container(border=True):
        st.subheader("Lancer un run")
        source = st.selectbox("Source", SOURCE_CHOICES, key="run_source")
        label = st.radio("Opération", list(START_STEPS) + ["Purge collection"], key="op")

        col1, col2 = st.columns(2)
        if col1.button("Lancer", type="primary", use_container_width=True):
            if label == "Purge collection":
                st.session_state["confirm_purge"] = True
            else:
                launch_ingest(source, label)
        if st.session_state.get("confirm_purge") and label == "Purge collection":
            col2.button(
                f"⚠️ Confirmer la purge de {config.get_collection(source)}",
                on_click=lambda s=source: purge_collection(s),
                use_container_width=True,
            )
        if col2.button("Actualiser", use_container_width=True):
            st.rerun()

    entry = st.session_state.get("active")
    if entry:
        rec = read_run(Path(entry["path"]))
        with st.container(border=True):
            st.subheader(f"Run actif — {entry['source']} ({entry['label']})")
            if rec is None:
                st.info("Démarrage du runner…")
            else:
                render_run(rec)
            if st.button("⏹️ Arrêter (kill)", key="kill"):
                kill_active(entry)
                st.rerun()
        if rec is not None and rec.get("status") not in TERMINAL:
            time.sleep(2)
            st.rerun()
        elif rec is not None and rec.get("status") in TERMINAL:
            st.session_state.pop("active", None)
            st.rerun()

    with st.container(border=True):
        st.subheader("Historique des runs")
        render_history()


if __name__ == "__main__":
    main()
```

Note : le `on_click` avec `lambda s=source` capture la valeur au clic ; c'est cohérent car `source` est figé par le `selectbox` du rerun courant.

- [ ] **Étape 4 : vérifier la syntaxe.**

Run : `python -m py_compile admin/app.py admin/Dockerfile 2>/dev/null || python -m py_compile admin/app.py`
Attendu : py_compile OK pour `admin/app.py` (le Dockerfile n'est pas du Python ; ne compiler que `admin/app.py`).

- [ ] **Étape 5 : commit.**

```bash
git add admin/app.py admin/requirements.txt admin/Dockerfile
git commit -m "feat(admin): app Streamlit de pilotage (lancer/suivre/arrêter/purger/historique)"
```

---

### Tâche 6 : Mise à jour de CLAUDE.md + validation finale

**Fichiers :**
- Modifier : `CLAUDE.md`

- [ ] **Étape 1 : mettre à jour CLAUDE.md.** Dans « Évolution planifiée » :
1. L'intro : remplacer « Reste **non implémentée** : la **Phase B** (administration). » par « La **Phase B — Administration** est **implémentée en v1 (pilotage + statut)** : `admin/`, `app/status_writer.py`, `app/runner.py`. **Différé** : la stratégie de fraîcheur incrémentale (pages modifiées/disparues), le scheduler et la purge ciblée. »
2. Sous le titre `### Phase B — Administration (app Streamlit séparée)` : remplacer le bloc par la version implémentée :

```markdown
### Phase B — Administration (implémentée, v1 pilotage + statut)

- **App dédiée** `admin/app.py` (pas une page de `chatbot/app.py`) qui pilote le pipeline : lance un run en **sous-processus**, suit sa progression **temps réel**, permet de l'**arrêter**, **purge** une collection Weaviate et garde un **historique**.
- **Un run = une source**, exécuté dans **un seul process** par `app/runner.py` (`get_docs → chunk_docs → ingest_weaviate`), avec **points de départ avancés** (dès le chunking / dès l'ingestion : pas de re-téléchargement).
- **`app/status_writer.py`** (utilitaire partagé) écrit un fichier JSON par run dans `data/status/{run_id}_{source}.json` (+ pointeur `latest.json`), **atomiquement**. Contenu : `run_id`, `source`, `operation` (ingest | purge), `start_step`, `steps`, `status` (running/done/failed/cancelled), `pid`, timestamps, `step`, `step_progress` {done,total}, `last_message`, `error`. Historique borné à `RUNS_HISTORY` (10).
- **Instrumentation optionnelle** : les scripts exposent `run(source, status=None)` ; sans `status`, comportement CLI inchangé. Les extracteurs exposent une progression optionnelle.
- **Planification : manuelle uniquement.**
- **Différé (non implémenté)** : stratégie de fraîcheur hybride (diff `lastmod`/git/archive des pages modifiées + suppression des pages disparues), scheduler, purge ciblée.
```

3. Dans « Commandes », ajouter après la section chatbot conteneurisé :

```markdown
# Admin pipeline — en développement (dans admin/, depuis la racine)
streamlit run admin/app.py

# Admin pipeline — conteneurisé
docker build -f admin/Dockerfile . -t personal_admin
docker run -e PORT=7863 -p 7863:7863 personal_admin
# → http://localhost:7863/
```

4. Dans « Architecture », après la sous-section `### Chatbot …`, ajouter une ligne renvoyant à la Phase B (optionnel, courte) :

```markdown
### Administration (`admin/app.py`, `app/runner.py`, `app/status_writer.py`)

App Streamlit séparée qui pilote le pipeline (cf. section Phase B ci-dessus).
```

- [ ] **Étape 2 : lancer toute la suite de tests.**

Run : `python -m pytest -q`
Attendu : PASS (tests des tâches 1–4 + régressions).

- [ ] **Étape 3 : validation manuelle (host-side).** Lancer l'app et suivre un run réel en vérifiant les fichiers de statut :

```bash
# 1) Sous-processus simple via le runner (ré-ingestion TypeScript idempotente, chunks existants)
python app/runner.py --source typescript --run-id manual-ts-$(date +%Y%m%dT%H%M%S) --operation ingest --start-step ingest_weaviate

# 2) Statut final attendu : done
python -c "import json,glob; print(json.load(open(sorted(glob.glob('data/status/*.json'))[-1]))['status'])"
```

Puis, dans un second terminal :

```bash
streamlit run admin/app.py
```

Vérifier manuellement dans le navigateur : liste des sources avec comptage, lancement d'un run « Dès l'ingestion » sur `typescript`, barre de progression, passage en `done`, historique renseigné. (La purge n'est pas testée pour ne pas perdre de données ; suppression d'une collection inexistante = no-op.)

- [ ] **Étape 4 : commit.**

```bash
git add CLAUDE.md
git commit -m "docs: Phase B implémentée (v1 pilotage + statut) + commandes admin"
```

---

## Auto-revue

- **Couverture spec** : modèle de run (§2) → tâche 1 ; instrumentation/scripts (§3) → tâches 2–3 ; runner (§4) → tâche 4 ; UI + purge (§5–6) → tâche 5 ; erreurs/cas limites (§7) gérés dans `execute_run`, `kill_active`, `collection_counts`, appels atomiques ; tests (§8) → tâches 1–4 ; config/docs (.gitignore, CLAUDE.md, §9) → tâches 1 et 6. Périmètre différé (fraîcheur, scheduler, purge ciblée, build Docker) → volontairement absent.
- **Types cohérents** : `RunReporter.progress(done, total)`/`.message(text)` ; `run(source_name, status=None)` ; `extract(progress=None)` ; `ingest_file(..., progress=None)` ; `execute_run(*, run_id, source, operation, start_step, status_dir, run_funcs)` ; `status_path(status_dir, run_id, source)`.
- **Pas de placeholders** : chaque étape de code est fournie intégralement.
