# Pipeline Multi-Sources — Plan d'implémentation

> **Pour les agents exécutants :** SUB-SKILL REQUIS : utiliser `superpowers:subagent-driven-development` (recommandé) ou `superpowers:executing-plans` pour implémenter ce plan tâche par tâche. Les étapes utilisent la syntaxe à cocher (`- [ ]`).

**Goal :** Refondre le pipeline d'ingestion (`app/`) pour qu'il ingère plusieurs sources de documentation de types différents (sitemap, dépôt git, archive zip) via une config data-driven.

**Architecture :** `app/config/config.py` passe d'« une source active + blocs commentés » à une liste `SOURCES` data-driven. Les trois mécaniques d'extraction sont encapsulées derrière une classe abstraite `BaseExtractor` (`app/extractors/`) avec héritage — `SitemapExtractor`, `GitExtractor`, `ArchiveExtractor`. `get_docs.py`, `chunk_docs.py` et `ingest_weaviate.py` deviennent des dispatchs paramétrés par `--source <name>`. L'extraction HTML est généralisée via un sélecteur de contenu (`content_selector`) par source.

**Tech Stack :** Python 3.12, `langchain-community` (SitemapLoader), `beautifulsoup4` + `lxml` (parsing HTML), `transformers` + `sentence-transformers` (tokenizer/embeddings), `weaviate-client`, `pytest` (nouveau, dev).

**Spec :** `CLAUDE.md` → section « Évolution planifiée (non implémentée) » → « Phase A — Multi-sources ». Le plan argumente depuis la spec ; l'exécuteur lit les deux.

## Global Constraints

- La liste `SOURCES` contient exactement 5 sources : `snowflake`, `databricks`, `nextjs` (type `sitemap`), `typescript` (type `git`), `python` (type `archive`). Les noms sont en minuscules, sans espace.
- Patterns de fichiers **dérivés du nom** : `{name}_docs_batch_` et `{name}_chunks_batch_` (cohérent avec les fichiers existants `snowflake_docs_batch_*.jsonl`).
- Chaque source a une `collection` Weaviate unique. Noms de collections : `SnowflakeDocs`, `DatabricksDocs`, `NextJSDocs`, `TypeScriptDocs`, `PythonDocs`.
- Les constantes globales de config (`WEAVIATE_HOST`, ports, `BATCH_SIZE_*`, `EMBEDDING_*`, `CHUNK_*`, `RAW_DATA_DIR`, `CHUNKS_DATA_DIR`, `JSONL_EXT`) sont conservées telles quelles.
- L'environnement d'ingestion reste Conda + Python 3.12 ; lancer les scripts depuis la racine du repo (`python app/<script>.py --source <name>`).
- Le contenu HTML est extrait via `content_selector` (`"article"` ou `"[role='main']"` selon la source).
- Dépôts git et archives téléchargés vont dans `data/raw_src/{name}/` (à git-ignorer). Les fichiers intermédiaires `data/raw/` et `data/chunks/` restent au format JSONL, ignorés par git (`/data/**/*.jsonl`).
- Les tests automatisés (pytest) ne doivent **pas** nécessiter de réseau, GPU, Weaviate ni téléchargement HuggingFace.

## File Structure

- Create: `app/extractors/__init__.py` — package extracteurs
- Create: `app/extractors/base.py` — `BaseExtractor` (abstrait) + sauvegarde batch partagée
- Create: `app/extractors/html_content.py` — extraction de texte depuis un BeautifulSoup via sélecteur
- Create: `app/extractors/sitemap.py` — `SitemapExtractor`
- Create: `app/extractors/git.py` — `GitExtractor`
- Create: `app/extractors/archive.py` — `ArchiveExtractor`
- Modify: `app/config/config.py` — liste `SOURCES` + accesseurs, suppression des constantes mono-source
- Modify: `app/get_docs.py` — dispatcher `--source` instanciant l'extracteur du bon type
- Modify: `app/chunk_docs.py` — paramétré par `--source`, splitter/tokenizer injectables (testabilité)
- Modify: `app/ingest_weaviate.py` — paramétré par `--source` (collection + pattern dérivés)
- Modify: `app/query_weaviate.py` — `--collection` au lieu de `config.COLLECTION_NAME`
- Create: `requirements-dev.txt` — `pytest`
- Create: `pytest.ini` — config pytest (racine)
- Create: `tests/conftest.py` — ajoute `app/` au `sys.path`
- Create: `tests/test_config.py` — validation de `SOURCES`
- Create: `tests/test_html_content.py` — extraction via sélecteur
- Create: `tests/test_sitemap_extractor.py` — avec `loader_factory` mocké
- Create: `tests/test_git_extractor.py` — avec un dépôt git local temporaire
- Create: `tests/test_archive_extractor.py` — avec un zip local temporaire
- Create: `tests/test_chunk_docs.py` — `make_chunk_id` + `chunk_one_record` (splitter/tokenizer factices)
- Create: `tests/test_ingest_helpers.py` — `batch_iterable` + `read_jsonl_file`
- Modify: `.gitignore` — ajouter `/data/raw_src/`

Responsabilités : `app/extractors/*` ne font que produire des fichiers JSONL bruts dans `data/raw/` ; `chunk_docs.py` ne fait que chunker ; `ingest_weaviate.py` ne fait qu'embedder + insérer. Chaque fichier a une seule responsabilité.

---

### Task 1: Infrastructure de test (pytest)

**Files:**
- Create: `requirements-dev.txt`
- Create: `pytest.ini`
- Create: `tests/conftest.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: rien (bootstrap)
- Produces: `pytest` exécutable à la racine ; `tests/conftest.py` garantit que `import config.config`, `from extractors.base import ...` fonctionnent depuis `tests/`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/conftest.py
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP_DIR))
```

```python
# tests/test_config.py
import config.config as config


def test_sources_is_list_of_dicts():
    assert isinstance(config.SOURCES, list)
    assert len(config.SOURCES) == 5
    assert all(isinstance(s, dict) for s in config.SOURCES)
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError: module 'config.config' has no attribute 'SOURCES'`

- [ ] **Step 3: Créer `pytest.ini` et `requirements-dev.txt`**

```ini
# pytest.ini
[pytest]
testpaths = tests
```

```text
# requirements-dev.txt
pytest
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL (toujours) — `SOURCES` n'existe pas encore ; c'est attendu : le fichier de test valide un contrat non implémenté. La Task 2 le fera passer.

- [ ] **Step 5: Commit**

```bash
git add requirements-dev.txt pytest.ini tests/conftest.py tests/test_config.py
git commit -m "test: bootstrap pytest et contrat SOURCES"
```

---

### Task 2: Config data-driven — `app/config/config.py`

**Files:**
- Modify: `app/config/config.py`
- Test: `tests/test_config.py` (compléter)

**Interfaces:**
- Consumes: rien
- Produces:
  - `config.SOURCES` — `list[dict]`, 5 sources, clés : `name`, `type` (`sitemap`|`git`|`archive`), `collection`, `content_selector`, et clés spécifiques (`sitemap_url`+`filter_urls` pour sitemap ; `repo_url`+`branch`+`docs_path` pour git ; `archive_url` pour archive)
  - `config.get_source(name: str) -> dict` — lève `KeyError` si inconnue
  - `config.get_collection(name: str) -> str` — collection de la source

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# tests/test_config.py (ajout)
import config.config as config


def test_sources_have_required_keys():
    required = {"name", "type", "collection", "content_selector"}
    for source in config.SOURCES:
        assert required.issubset(source.keys())


def test_source_names_unique():
    names = [s["name"] for s in config.SOURCES]
    assert len(names) == len(set(names))


def test_sources_by_type():
    types = {s["type"] for s in config.SOURCES}
    assert types == {"sitemap", "git", "archive"}


def test_get_source_returns_dict():
    assert config.get_source("typescript")["type"] == "git"


def test_get_source_unknown_raises():
    import pytest

    with pytest.raises(KeyError):
        config.get_source("inexistant")


def test_get_collection():
    assert config.get_collection("python") == "PythonDocs"
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError: 'SOURCES'`

- [ ] **Step 3: Réécrire `app/config/config.py`**

```python
# Constantes globales (indépendantes de la source)
JSONL_EXT = "jsonl"

WEAVIATE_HOST = "localhost"
WEAVIATE_PORT = 9090
WEAVIATE_GRPC_PORT = 50051

RAW_DATA_DIR = "./data/raw"
CHUNKS_DATA_DIR = "./data/chunks"
RAW_SRC_DIR = "./data/raw_src"

CHUNK_TOKENIZER = "sentence-transformers/all-mpnet-base-v2"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 75
MAX_TOKEN_SIZE = 512

BATCH_SIZE_DOCS = 500
BATCH_SIZE_WEAVIATE = 100
EMBEDDING_MODEL_NAME = "sentence-transformers/all-mpnet-base-v2"
EMBEDDING_DEVICE = "cuda:0"
NORMALIZE_EMBEDDINGS = True

# Sources de documentation
SOURCES = [
    {
        "name": "snowflake",
        "type": "sitemap",
        "sitemap_url": "https://docs.snowflake.com/sitemap.xml",
        "filter_urls": [r"https://docs\.snowflake\.com/en/.*"],
        "collection": "SnowflakeDocs",
        "content_selector": "article",
    },
    {
        "name": "databricks",
        "type": "sitemap",
        "sitemap_url": "https://docs.databricks.com/en/doc-sitemap.xml",
        "filter_urls": [r"https://docs\.databricks\.com/aws/en/.*"],
        "collection": "DatabricksDocs",
        "content_selector": "article",
    },
    {
        "name": "nextjs",
        "type": "sitemap",
        "sitemap_url": "https://nextjs.org/sitemap.xml",
        "filter_urls": [r"https://nextjs\.org/docs/.*"],
        "collection": "NextJSDocs",
        "content_selector": "article",
    },
    {
        "name": "typescript",
        "type": "git",
        "repo_url": "https://github.com/microsoft/TypeScript-Website.git",
        "branch": "v2",
        "docs_path": "packages/documentation/copy/en",
        "collection": "TypeScriptDocs",
        "content_selector": None,
    },
    {
        "name": "python",
        "type": "archive",
        "archive_url": "https://docs.python.org/3.14/archives/python-3.14-docs-html.zip",
        "collection": "PythonDocs",
        "content_selector": "[role='main']",
    },
]


def get_source(name: str) -> dict:
    for source in SOURCES:
        if source["name"] == name:
            return source
    raise KeyError(f"Source inconnue: {name}")


def get_collection(name: str) -> str:
    return get_source(name)["collection"]


def docs_pattern(name: str) -> str:
    return f"{name}_docs_batch_"


def chunks_pattern(name: str) -> str:
    return f"{name}_chunks_batch_"
```

Note : le sélecteur `content_selector` de `nextjs` est `"article"` à **vérifier** lors du smoke test (Task 8) ; s'il ne correspond pas, ajuster la config.

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add app/config/config.py tests/test_config.py
git commit -m "feat(config): liste SOURCES data-driven + accesseurs"
```

---

### Task 3: `BaseExtractor` + extraction HTML

**Files:**
- Create: `app/extractors/__init__.py`
- Create: `app/extractors/base.py`
- Create: `app/extractors/html_content.py`
- Test: `tests/test_html_content.py`

**Interfaces:**
- Consumes: `config.docs_pattern(name)` (Task 2)
- Produces:
  - `extractors.base.BaseExtractor(source: dict, raw_dir: Path, batch_size: int)` — `name: str`, `docs_pattern: str` (property), `_save_batch(records: list[dict], batch_num: int) -> Path`, `extract() -> list[Path]` (abstrait)
  - `extractors.html_content.extract_from_soup(soup: BeautifulSoup, selector: str | None) -> str`

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# tests/test_html_content.py
from bs4 import BeautifulSoup

from extractors.html_content import extract_from_soup


def test_extract_from_article():
    html = "<article><h1>Titre</h1><p>Para 1</p><p>Para 2</p></article><nav>menu</nav>"
    soup = BeautifulSoup(html, "lxml")
    result = extract_from_soup(soup, "article")
    assert "Titre" in result
    assert "Para 1" in result
    assert "menu" not in result


def test_extract_from_role_main():
    html = '<div role="main"><p>Contenu Sphinx</p></div><footer>pied</footer>'
    soup = BeautifulSoup(html, "lxml")
    result = extract_from_soup(soup, "[role='main']")
    assert "Contenu Sphinx" in result
    assert "pied" not in result


def test_extract_empty_when_selector_missing():
    html = "<article></article>"
    soup = BeautifulSoup(html, "lxml")
    assert extract_from_soup(soup, "article") == ""


def test_extract_none_selector_falls_back_to_article():
    html = "<article><p>Fallback</p></article>"
    soup = BeautifulSoup(html, "lxml")
    assert "Fallback" in extract_from_soup(soup, None)
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python -m pytest tests/test_html_content.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'extractors'`

- [ ] **Step 3: Écrire les modules**

```python
# app/extractors/__init__.py
"""Extracteurs de documentation — un par type de source."""
```

```python
# app/extractors/html_content.py
from bs4 import BeautifulSoup


def extract_from_soup(soup: BeautifulSoup, selector: str | None) -> str:
    """Extrait le texte du conteneur principal d'un HTML.

    Args:
        soup (BeautifulSoup): Le document parsé.
        selector (str | None): Sélecteur CSS (ex: "article", "[role='main']").
            Si None, retombe sur la balise <article>.

    Returns:
        str: Le texte avec un retour à la ligne par paragraphe, ou "".
    """
    if selector:
        element = soup.select_one(selector)
    else:
        element = soup.find("article")

    if not element:
        return ""

    return element.get_text(separator="\n", strip=True)
```

```python
# app/extractors/base.py
import json
from abc import ABC, abstractmethod
from pathlib import Path

from config.config import docs_pattern


class BaseExtractor(ABC):
    """Interface commune des extracteurs de documentation.

    Chaque extracteur produit des fichiers JSONL bruts dans `raw_dir`
    suivant le pattern `{name}_docs_batch_{batch:03d}.jsonl`, avec une
    ligne par document : {source, loc, lastmod, content}.
    """

    def __init__(self, source: dict, raw_dir: Path, batch_size: int = 500):
        self.source = source
        self.name = source["name"]
        self.raw_dir = raw_dir
        self.batch_size = batch_size
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    @property
    def docs_pattern(self) -> str:
        return docs_pattern(self.name)

    def _save_batch(self, records: list[dict], batch_num: int) -> Path:
        out_file = self.raw_dir / f"{self.docs_pattern}{batch_num:03d}.jsonl"
        with out_file.open("w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return out_file

    @abstractmethod
    def extract(self) -> list[Path]:
        """Extrait les documents et écrit les fichiers JSONL bruts.

        Returns:
            list[Path]: Les chemins des fichiers batch écrits.
        """
        raise NotImplementedError
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_html_content.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add app/extractors/ tests/test_html_content.py
git commit -m "feat(extractors): BaseExtractor abstrait + extraction HTML par sélecteur"
```

---

### Task 4: `SitemapExtractor` + dispatcher `get_docs.py`

**Files:**
- Create: `app/extractors/sitemap.py`
- Modify: `app/get_docs.py`
- Test: `tests/test_sitemap_extractor.py`

**Interfaces:**
- Consumes: `BaseExtractor` (Task 3), `extract_from_soup` (Task 3), `config.BATCH_SIZE_DOCS`
- Produces:
  - `extractors.sitemap.SitemapExtractor(source, raw_dir, batch_size=500, requests_per_second=1, loader_factory=SitemapLoader)` — `loader_factory` injectable pour les tests
  - `get_docs.py` : CLI `python app/get_docs.py --source <name>` ; instancie l'extracteur via un registre `{"sitemap": SitemapExtractor, "git": GitExtractor, "archive": ArchiveExtractor}` (GitExtractor/ArchiveExtractor ajoutés aux Tasks 5-6)

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_sitemap_extractor.py
from pathlib import Path

from extractors.sitemap import SitemapExtractor


class FakeDoc:
    def __init__(self, content, source, loc, lastmod):
        self.page_content = content
        self.metadata = {"source": source, "loc": loc, "lastmod": lastmod}


class FakeLoader:
    def __init__(self, docs):
        self._docs = docs

    def load(self):
        return self._docs


def test_sitemap_extractor_writes_batches(tmp_path):
    batches = [
        [
            FakeDoc("Contenu page A", "https://x.com/a", "a", "2026-01-01"),
            FakeDoc("Contenu page B", "https://x.com/b", "b", "2026-01-02"),
        ],
        [],
    ]
    calls = {"n": 0}

    def loader_factory(**kwargs):
        docs = batches[calls["n"]]
        calls["n"] += 1
        return FakeLoader(docs)

    source = {
        "name": "nextjs",
        "type": "sitemap",
        "sitemap_url": "https://nextjs.org/sitemap.xml",
        "filter_urls": [r"https://nextjs\.org/docs/.*"],
        "collection": "NextJSDocs",
        "content_selector": "article",
    }

    extractor = SitemapExtractor(source, tmp_path, batch_size=500, loader_factory=loader_factory)
    written = extractor.extract()

    assert len(written) == 1
    lines = written[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    import json

    record = json.loads(lines[0])
    assert record["source"] == "https://x.com/a"
    assert record["lastmod"] == "2026-01-01"
    assert record["content"] == "Contenu page A"


def test_sitemap_extractor_resumes_at_next_batch(tmp_path):
    # Un batch 000 déjà présent => on écrit à partir du batch 001
    (tmp_path / "nextjs_docs_batch_000.jsonl").write_text(
        '{"source":"https://x.com/old","loc":"old","lastmod":null,"content":"old"}\n',
        encoding="utf-8",
    )

    def loader_factory(**kwargs):
        return FakeLoader([FakeDoc("nouveau", "https://x.com/new", "new", "2026-02-01")])

    source = {
        "name": "nextjs",
        "type": "sitemap",
        "sitemap_url": "https://nextjs.org/sitemap.xml",
        "filter_urls": [r"https://nextjs\.org/docs/.*"],
        "collection": "NextJSDocs",
        "content_selector": "article",
    }
    extractor = SitemapExtractor(source, tmp_path, batch_size=500, loader_factory=loader_factory)
    written = extractor.extract()

    assert len(written) == 1
    assert written[0].name == "nextjs_docs_batch_001.jsonl"
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python -m pytest tests/test_sitemap_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'extractors.sitemap'`

- [ ] **Step 3: Écrire `app/extractors/sitemap.py`**

```python
from pathlib import Path

from bs4 import BeautifulSoup
from langchain_community.document_loaders.sitemap import SitemapLoader

from extractors.base import BaseExtractor
from extractors.html_content import extract_from_soup


class SitemapExtractor(BaseExtractor):
    """Extrait les documents d'un sitemap via SitemapLoader (batch par batch)."""

    def __init__(
        self,
        source: dict,
        raw_dir: Path,
        batch_size: int = 500,
        requests_per_second: int = 1,
        loader_factory=SitemapLoader,
    ):
        super().__init__(source, raw_dir, batch_size)
        self.sitemap_url = source["sitemap_url"]
        self.filter_urls = source.get("filter_urls", [])
        self.selector = source.get("content_selector", "article")
        self.requests_per_second = requests_per_second
        self.loader_factory = loader_factory

    def _parsing_function(self, content: BeautifulSoup) -> str:
        return extract_from_soup(content, self.selector)

    def _find_next_batch_num(self) -> int:
        existing = sorted(self.raw_dir.glob(f"{self.docs_pattern}*.jsonl"))
        if not existing:
            return 0
        last_name = existing[-1].name
        # last_name: "nextjs_docs_batch_003.jsonl" -> 003
        batch_str = last_name.split("_")[-1].split(".")[0]
        return int(batch_str) + 1

    def _make_loader(self, blocknum: int):
        loader = self.loader_factory(
            web_path=self.sitemap_url,
            filter_urls=self.filter_urls,
            restrict_to_same_domain=True,
            continue_on_failure=True,
            requests_per_second=self.requests_per_second,
            blocksize=self.batch_size,
            blocknum=blocknum,
            parsing_function=self._parsing_function,
        )
        loader.requests_kwargs = {
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36",
            },
            "timeout": 30,
        }
        return loader

    def extract(self) -> list[Path]:
        written: list[Path] = []
        blocknum = self._find_next_batch_num()

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
            blocknum += 1

        return written
```

- [ ] **Step 4: Remplacer `app/get_docs.py` par le dispatcher**

```python
import argparse
from pathlib import Path

import config.config as config
from config.logger_config import setup_logging
from extractors.archive import ArchiveExtractor
from extractors.git import GitExtractor
from extractors.sitemap import SitemapExtractor

logger = setup_logging(__name__)

EXTRACTORS = {
    "sitemap": SitemapExtractor,
    "git": GitExtractor,
    "archive": ArchiveExtractor,
}


def main():
    parser = argparse.ArgumentParser(description="Extraction des docs d'une source")
    parser.add_argument(
        "--source",
        required=True,
        choices=[source["name"] for source in config.SOURCES],
        help="Nom de la source à extraire",
    )
    args = parser.parse_args()

    source = config.get_source(args.source)
    extractor_cls = EXTRACTORS[source["type"]]
    extractor = extractor_cls(
        source,
        raw_dir=Path(config.RAW_DATA_DIR),
        batch_size=config.BATCH_SIZE_DOCS,
    )

    logger.info(f"Début de l'extraction de la source '{args.source}' ({source['type']})")
    written = extractor.extract()
    logger.info(f"Terminé : {len(written)} fichier(s) batch écrit(s) pour '{args.source}'")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_sitemap_extractor.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Vérifier l'import du dispatcher (les extracteurs git/archive n'existent pas encore)**

Run: `python -c "import ast; ast.parse(open('app/get_docs.py').read())"`
Expected: PASSE (parse syntaxique). *L'exécution complète attend la Task 6.* Note : pour lancer réellement `get_docs.py`, il faut que `extractors.git` et `extractors.archive` existent — ils arrivent aux Tasks 5-6.

- [ ] **Step 7: Commit**

```bash
git add app/extractors/sitemap.py app/get_docs.py tests/test_sitemap_extractor.py
git commit -m "feat(extractors): SitemapExtractor + dispatcher get_docs"
```

---

### Task 5: `GitExtractor`

**Files:**
- Create: `app/extractors/git.py`
- Test: `tests/test_git_extractor.py`

**Interfaces:**
- Consumes: `BaseExtractor` (Task 3), `config.RAW_SRC_DIR`
- Produces:
  - `extractors.git.GitExtractor(source, raw_dir, batch_size=500, cache_dir: Path | None = None)` — clone `repo_url` (branch `branch`) dans `cache_dir` (défaut `data/raw_src/{name}`), lit les `.md` sous `docs_path` ; `lastmod` = date du dernier commit (format ISO). `extract() -> list[Path]`.
  - Format de sortie par ligne : `{"source": <URL blob GitHub>, "loc": <chemin relatif>, "lastmod": <ISO|None>, "content": <markdown>}`

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_git_extractor.py
import subprocess
from pathlib import Path

from extractors.git import GitExtractor


def make_local_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@test.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    (repo / "docs").mkdir()
    (repo / "docs" / "intro.md").write_text("# Intro\nTexte d'intro.", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True)
    return repo


def test_git_extractor_reads_markdown(tmp_path):
    repo = make_local_repo(tmp_path)
    source = {
        "name": "typescript",
        "type": "git",
        "repo_url": str(repo),
        "branch": "master",
        "docs_path": "docs",
        "collection": "TypeScriptDocs",
        "content_selector": None,
    }
    extractor = GitExtractor(source, tmp_path / "raw", batch_size=500)
    written = extractor.extract()

    assert len(written) == 1
    lines = written[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    import json

    record = json.loads(lines[0])
    assert record["loc"] == "intro.md"
    assert "# Intro" in record["content"]
    assert record["lastmod"] is not None
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `python -m pytest tests/test_git_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'extractors.git'`

- [ ] **Step 3: Écrire `app/extractors/git.py`**

```python
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from extractors.base import BaseExtractor


class GitExtractor(BaseExtractor):
    """Extrait les documents markdown d'un dépôt git (clone shallow + fetch)."""

    def __init__(
        self,
        source: dict,
        raw_dir: Path,
        batch_size: int = 500,
        cache_dir: Path | None = None,
    ):
        super().__init__(source, raw_dir, batch_size)
        self.repo_url = source["repo_url"]
        self.branch = source.get("branch")
        self.docs_path = source["docs_path"]
        self.cache_dir = cache_dir or (raw_dir.parent / "raw_src" / self.name)

    def _clone_or_fetch(self) -> Path:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if (self.cache_dir / ".git").exists():
            subprocess.run(["git", "fetch", "origin", self.branch], cwd=self.cache_dir, check=True)
        else:
            subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", self.branch, self.repo_url, str(self.cache_dir)],
                check=True,
            )
        subprocess.run(["git", "-C", str(self.cache_dir), "checkout", "-q", self.branch], check=True)
        return self.cache_dir

    def _last_modified(self, rel_path: Path) -> str | None:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", str(rel_path)],
            cwd=self.cache_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        value = result.stdout.strip()
        return value or None

    def _blob_url(self, rel_path: Path) -> str:
        parsed = urlparse(self.repo_url)
        if parsed.scheme in ("http", "https"):
            host = parsed.netloc
            path = parsed.path.rstrip("/")
            return f"https://{host}{path}/blob/{self.branch}/{rel_path.as_posix()}"
        # dépôt local (tests) : URL inutilisable, on retombe sur un chemin
        return f"file://{self.cache_dir}/{rel_path.as_posix()}"

    def extract(self) -> list[Path]:
        repo = self._clone_or_fetch()
        docs_root = repo / self.docs_path
        md_files = sorted(docs_root.rglob("*.md"))

        written: list[Path] = []
        batch: list[dict] = []
        batch_num = 0

        for md_file in md_files:
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

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `python -m pytest tests/test_git_extractor.py -v`
Expected: PASS (1 test). *Si `git` n'est pas trouvé ou échoue sur Windows, vérifier que `git` est dans le PATH et que `--depth 1 --branch master` fonctionne sur un dépôt local.*

- [ ] **Step 5: Commit**

```bash
git add app/extractors/git.py tests/test_git_extractor.py
git commit -m "feat(extractors): GitExtractor pour les docs markdown en dépôt git"
```

---

### Task 6: `ArchiveExtractor`

**Files:**
- Create: `app/extractors/archive.py`
- Test: `tests/test_archive_extractor.py`

**Interfaces:**
- Consumes: `BaseExtractor` (Task 3), `extract_from_soup` (Task 3), `config.RAW_SRC_DIR`
- Produces:
  - `extractors.archive.ArchiveExtractor(source, raw_dir, batch_size=500, cache_dir: Path | None = None)` — télécharge `archive_url` (ou copie si chemin local) dans `cache_dir`, dézippe, parse les `.html` avec `content_selector`. `extract() -> list[Path]`.
  - Format par ligne : `{"source": <URL base>/<chemin html>, "loc": <chemin>, "lastmod": null, "content": <texte>}`. URL base = `archive_url` moins la partie `/archives/<fichier>`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_archive_extractor.py
import zipfile
from pathlib import Path

from extractors.archive import ArchiveExtractor


def make_local_zip(root: Path) -> Path:
    archive = root / "python-3.14-docs-html.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(
            "library/os.html",
            '<html><body><div role="main"><h1>os</h1><p>Module OS.</p></div></body></html>',
        )
        zf.writestr(
            "tutorial/index.html",
            '<html><body><div role="main"><p>Tutoriel.</p></div></body></html>',
        )
    return archive


def test_archive_extractor_parses_html(tmp_path):
    archive = make_local_zip(tmp_path)
    source = {
        "name": "python",
        "type": "archive",
        "archive_url": f"https://docs.python.org/3.14/archives/{archive.name}",
        "collection": "PythonDocs",
        "content_selector": "[role='main']",
    }

    extractor = ArchiveExtractor(source, tmp_path / "raw", batch_size=500, cache_dir=tmp_path / "src")
    written = extractor.extract()

    # cache_dir existe et contient l'archive copiée
    assert (tmp_path / "src" / archive.name).exists()

    assert len(written) == 1
    lines = written[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    import json

    record = json.loads(lines[0])
    assert record["source"] == "https://docs.python.org/3.14/library/os.html"
    assert "Module OS." in record["content"]
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `python -m pytest tests/test_archive_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'extractors.archive'`

- [ ] **Step 3: Écrire `app/extractors/archive.py`**

```python
import shutil
import urllib.request
import zipfile
from pathlib import Path

from bs4 import BeautifulSoup

from extractors.base import BaseExtractor
from extractors.html_content import extract_from_soup


class ArchiveExtractor(BaseExtractor):
    """Extrait les documents d'une archive HTML (.zip) téléchargée."""

    def __init__(
        self,
        source: dict,
        raw_dir: Path,
        batch_size: int = 500,
        cache_dir: Path | None = None,
    ):
        super().__init__(source, raw_dir, batch_size)
        self.archive_url = source["archive_url"]
        self.selector = source.get("content_selector", "article")
        self.cache_dir = cache_dir or (raw_dir.parent / "raw_src" / self.name)

    def _download(self) -> Path:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        filename = self.archive_url.rstrip("/").split("/")[-1]
        dest = self.cache_dir / filename
        if dest.exists():
            return dest
        local_candidate = Path(self.archive_url)
        if local_candidate.exists():
            shutil.copyfile(local_candidate, dest)
        else:
            urllib.request.urlretrieve(self.archive_url, dest)
        return dest

    def _extract_zip(self, archive: Path) -> Path:
        extract_dir = self.cache_dir / "extracted"
        if not extract_dir.exists():
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(extract_dir)
        return extract_dir

    def _base_url(self) -> str:
        # "https://docs.python.org/3.14/archives/python-3.14-docs-html.zip" -> "https://docs.python.org/3.14"
        if "/archives/" in self.archive_url:
            return self.archive_url.split("/archives/", 1)[0]
        return self.archive_url

    def extract(self) -> list[Path]:
        archive = self._download()
        root = self._extract_zip(archive)
        base_url = self._base_url()

        written: list[Path] = []
        batch: list[dict] = []
        batch_num = 0

        for html_file in sorted(root.rglob("*.html")):
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

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `python -m pytest tests/test_archive_extractor.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add app/extractors/archive.py tests/test_archive_extractor.py
git commit -m "feat(extractors): ArchiveExtractor pour les archives HTML zip"
```

---

### Task 7: Paramétrer `chunk_docs.py` par source (+ testabilité)

**Files:**
- Modify: `app/chunk_docs.py`
- Test: `tests/test_chunk_docs.py`

**Interfaces:**
- Consumes: `config.SOURCES`, `config.chunks_pattern(name)`, `config.docs_pattern(name)`, `config.JSONL_EXT`, constantes chunk (`CHUNK_SIZE`, etc.)
- Produces:
  - `chunk_docs.make_chunk_id(source: str, chunk_index: int, content: str) -> str` — SHA-1 de `{source}::{chunk_index}::{content}` (inchangé)
  - `chunk_docs.chunk_one_record(record: dict, splitter=None, tokenizer=None) -> list[dict]` — splitter/tokenizer injectables (défaut : globaux du module)
  - CLI : `python app/chunk_docs.py --source <name>` — lit `data/raw/{name}_docs_batch_*.jsonl`, écrit `data/chunks/{name}_chunks_batch_*.jsonl`

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# tests/test_chunk_docs.py
from chunk_docs import chunk_one_record, make_chunk_id


class FakeSplitter:
    def split_text(self, text: str):
        # découpe grossièrement en blocs de 10 caractères
        return [text[i : i + 10] for i in range(0, len(text), 10)]


class FakeTokenizer:
    def encode(self, text: str, **kwargs):
        return list(range(len(text)))


def test_make_chunk_id_is_deterministic():
    a = make_chunk_id("src", 3, "contenu")
    b = make_chunk_id("src", 3, "contenu")
    assert a == b
    assert len(a) == 40  # SHA-1 hex


def test_make_chunk_id_changes_with_content():
    assert make_chunk_id("src", 3, "a") != make_chunk_id("src", 3, "b")


def test_chunk_one_record_with_injected_splitter():
    record = {"source": "s", "loc": "l", "lastmod": "2026-01-01", "content": "0123456789ABCDEF"}
    chunks = chunk_one_record(record, splitter=FakeSplitter(), tokenizer=FakeTokenizer())
    assert len(chunks) == 2
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["source"] == "s"
    assert chunks[1]["chunk_index"] == 1


def test_chunk_one_record_skips_empty_content():
    record = {"source": "s", "content": "   "}
    assert chunk_one_record(record, splitter=FakeSplitter(), tokenizer=FakeTokenizer()) == []
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python -m pytest tests/test_chunk_docs.py -v`
Expected: FAIL — `chunk_one_record` ne gère pas `splitter`/`tokenizer` en paramètre (SignatureError) ou échec d'import si la fonction change.

- [ ] **Step 3: Modifier `app/chunk_docs.py`**

Remplacer les références aux constantes mono-source et la signature de `chunk_one_record` :

```python
import argparse
import hashlib
import json
from pathlib import Path

import config.config as config
from config.logger_config import setup_logging
from langchain_text_splitters import RecursiveCharacterTextSplitter
from transformers import AutoTokenizer
import os

logger = setup_logging(__name__)

os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

RAW_DIR = Path(config.RAW_DATA_DIR)
CHUNKS_DIR = Path(config.CHUNKS_DATA_DIR)

CHUNK_TOKENIZER = config.CHUNK_TOKENIZER
CHUNK_SIZE = config.CHUNK_SIZE
CHUNK_OVERLAP = config.CHUNK_OVERLAP
MAX_TOKEN_SIZE = config.MAX_TOKEN_SIZE

TOKENIZER = AutoTokenizer.from_pretrained(CHUNK_TOKENIZER, trust_remote_code=True)

SPLITTER = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
    TOKENIZER,
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", " ", ""],
)


def make_chunk_id(source, chunk_index, content):
    raw = f"{source}::{chunk_index}::{content}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def chunk_one_record(record, splitter=SPLITTER, tokenizer=TOKENIZER):
    source = record.get("source")
    loc = record.get("loc")
    lastmod = record.get("lastmod")
    content = record.get("content", "")

    output = []

    if not content or not content.strip():
        return output

    text_chunks = splitter.split_text(content)

    for chunk_index, chunk_text in enumerate(text_chunks):
        chunk_text = chunk_text.strip()

        if not chunk_text:
            continue

        n_tokens = len(tokenizer.encode(chunk_text, add_special_tokens=True))
        if n_tokens > MAX_TOKEN_SIZE:
            logger.warning(f"chunk trop long: {n_tokens} tokens (source={source}, index={chunk_index})")

        chunk_id = make_chunk_id(source or "unknown", chunk_index, chunk_text)

        output.append(
            {
                "chunk_id": chunk_id,
                "source": source,
                "loc": loc,
                "lastmod": lastmod,
                "chunk_index": chunk_index,
                "chunk_size": n_tokens,
                "content": chunk_text,
            }
        )

    return output


def main():
    parser = argparse.ArgumentParser(description="Découpe les docs brutes en chunks")
    parser.add_argument(
        "--source",
        required=True,
        choices=[source["name"] for source in config.SOURCES],
        help="Nom de la source à chunker",
    )
    args = parser.parse_args()

    docs_pattern = config.docs_pattern(args.source)
    chunks_pattern = config.chunks_pattern(args.source)

    total_docs = 0
    total_chunks = 0

    input_files = sorted(RAW_DIR.glob(f"{docs_pattern}*.{config.JSONL_EXT}"))
    logger.info(f"input_files : {input_files}")

    for input_file in input_files:
        output_file = CHUNKS_DIR / input_file.name.replace(docs_pattern, chunks_pattern)
        output_file.parent.mkdir(parents=True, exist_ok=True)

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

                    total_docs += 1
                    chunks = chunk_one_record(record)

                    for chunk in chunks:
                        fout.write(json.dumps(chunk, ensure_ascii=False) + "\n")

                    total_chunks += len(chunks)

                    if total_docs % 100 == 0:
                        logger.info(f"{input_file.name} : {total_docs} docs traités - {total_chunks} chunks créés")

        logger.info(f"Terminé {input_file.name} : {total_docs} docs - {total_chunks} chunks")

    logger.info("Terminé.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_chunk_docs.py -v`
Expected: PASS (4 tests). *Le module importe `AutoTokenizer` (download HF au premier run), mais les tests injectent un faux tokenizer — l'import du module déclenche quand même le téléchargement au chargement. Si l'environnement de test n'a pas la dépendance, l'import échoue : vérifier que l'environnement Conda a `transformers` et `langchain-text-splitters` (présents dans `requirements.txt`).*

- [ ] **Step 5: Commit**

```bash
git add app/chunk_docs.py tests/test_chunk_docs.py
git commit -m "feat(chunk): paramétré par source, splitter/tokenizer injectables"
```

---

### Task 8: Paramétrer `ingest_weaviate.py` par source

**Files:**
- Modify: `app/ingest_weaviate.py`
- Test: `tests/test_ingest_helpers.py`

**Interfaces:**
- Consumes: `config.SOURCES`, `config.get_collection(name)`, `config.chunks_pattern(name)`, `config.JSONL_EXT`, constantes weaviate/embedding
- Produces:
  - `ingest_weaviate.batch_iterable(records: Iterable, batch_size: int) -> Iterator[list]` (inchangé, testé)
  - `ingest_weaviate.read_jsonl_file(file_path: Path) -> Iterator[dict]` (inchangé, testé)
  - CLI : `python app/ingest_weaviate.py --source <name>` — lit `data/chunks/{name}_chunks_batch_*.jsonl`, collection = `get_collection(name)`

- [ ] **Step 1: Écrire les tests qui échouent (helpers purs)**

```python
# tests/test_ingest_helpers.py
import json

from ingest_weaviate import batch_iterable, read_jsonl_file


def test_batch_iterable_yields_full_batches():
    batches = list(batch_iterable(range(10), 3))
    assert batches == [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]


def test_batch_iterable_empty():
    assert list(batch_iterable([], 3)) == []


def test_read_jsonl_file(tmp_path):
    f = tmp_path / "data.jsonl"
    f.write_text(
        '{"a": 1}\n\n{"a": 2}\n',  # ligne vide ignorée
        encoding="utf-8",
    )
    records = list(read_jsonl_file(f))
    assert len(records) == 2
    assert records[0]["a"] == 1
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python -m pytest tests/test_ingest_helpers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingest_weaviate'` (le module n'est pas importable depuis `tests/` sans ajustement) *ou* échec si l'import du module dépend de Weaviate. Voir Step 3 : l'import doit rester léger.

- [ ] **Step 3: Modifier `app/ingest_weaviate.py`**

Remplacer le bloc d'en-tête (constantes mono-source) par :

```python
import argparse
import json
import uuid
from pathlib import Path

import config.config as config
import torch
import weaviate
from config.logger_config import setup_logging
from langchain_huggingface import HuggingFaceEmbeddings
from weaviate.classes.config import Configure, DataType, Property
from weaviate.classes.data import DataObject

logger = setup_logging(__name__)

CHUNKS_DATA_DIR = Path(config.CHUNKS_DATA_DIR)
WEAVIATE_HOST = config.WEAVIATE_HOST
WEAVIATE_PORT = config.WEAVIATE_PORT
WEAVIATE_GRPC_PORT = config.WEAVIATE_GRPC_PORT
BATCH_SIZE_WEAVIATE = config.BATCH_SIZE_WEAVIATE
EMBEDDING_MODEL_NAME = config.EMBEDDING_MODEL_NAME
EMBEDDING_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
NORMALIZE_EMBEDDINGS = config.NORMALIZE_EMBEDDINGS
```

(Conserver telles quelles les fonctions `get_embeddings`, `connect_client`, `get_collection` — mais `get_collection` doit recevoir `collection_name` en argument au lieu de lire `config.COLLECTION_NAME`.)

```python
def get_collection(client, collection_name: str):
    existing_coll = client.collections.list_all()

    if collection_name in existing_coll:
        logger.info(f"Collection '{collection_name}' existe déjà")
        return client.collections.get(collection_name)

    logger.info(f"Création de la collection '{collection_name}'...")

    client.collections.create(
        name=collection_name,
        properties=[
            Property(name="chunk_id", data_type=DataType.TEXT),
            Property(name="source", data_type=DataType.TEXT),
            Property(name="loc", data_type=DataType.TEXT),
            Property(name="lastmod", data_type=DataType.TEXT),
            Property(name="chunk_index", data_type=DataType.INT),
            Property(name="chunk_size", data_type=DataType.INT),
            Property(name="content", data_type=DataType.TEXT),
        ],
        vector_config=Configure.Vectors.self_provided(),
    )

    logger.info(f"Collection '{collection_name}' créée")
    return client.collections.get(collection_name)
```

Et le `main()` :

```python
def main():
    parser = argparse.ArgumentParser(description="Embedding + indexation Weaviate d'une source")
    parser.add_argument(
        "--source",
        required=True,
        choices=[source["name"] for source in config.SOURCES],
        help="Nom de la source à ingérer",
    )
    args = parser.parse_args()

    collection_name = config.get_collection(args.source)
    chunks_pattern = config.chunks_pattern(args.source)

    input_files = sorted(CHUNKS_DATA_DIR.glob(f"{chunks_pattern}*.{config.JSONL_EXT}"))

    if not input_files:
        logger.info(f"Aucun fichier {chunks_pattern}*.{config.JSONL_EXT} trouvé dans {CHUNKS_DATA_DIR}")
        return

    logger.info(f"{len(input_files)} fichiers trouvés dans {CHUNKS_DATA_DIR}")

    embeddings = get_embeddings()
    client = connect_client()

    try:
        weaviate_collection = get_collection(client, collection_name)

        for file_path in input_files:
            ingest_file(weaviate_collection, embeddings, file_path)

        logger.info(f"Ingestion Weaviate terminée pour '{args.source}'.")

    finally:
        client.close()
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_ingest_helpers.py -v`
Expected: PASS (3 tests). *L'import de `ingest_weaviate` charge `weaviate` et `torch` — l'environnement Conda les a déjà (pipeline d'ingestion). Aucun appel réseau : `connect_client` n'est appelé que dans `main()`.*

- [ ] **Step 5: Commit**

```bash
git add app/ingest_weaviate.py tests/test_ingest_helpers.py
git commit -m "feat(ingest): paramétré par source, collection dérivée de la config"
```

---

### Task 9: Adapter `query_weaviate.py`

**Files:**
- Modify: `app/query_weaviate.py`

**Interfaces:**
- Consumes: `config.SOURCES`, `config.get_collection(name)`
- Produces: CLI `python app/query_weaviate.py --collection <name>` (défaut : première collection de `SOURCES`)

- [ ] **Step 1: Modifier le script**

Remplacer la référence à `config.COLLECTION_NAME` (qui n'existe plus) :

```python
import argparse

import config.config as config
import weaviate
from langchain_huggingface import HuggingFaceEmbeddings
from weaviate.classes.query import MetadataQuery, Filter

QUERY_TEXT = "What is Unity Catalog?"
LIMIT = 3


def main():
    parser = argparse.ArgumentParser(description="Test jetable de la recherche hybride")
    parser.add_argument(
        "--collection",
        default=config.get_collection(config.SOURCES[0]["name"]),
        help="Collection Weaviate à interroger",
    )
    args = parser.parse_args()

    embeddings = HuggingFaceEmbeddings(
        model_name=config.EMBEDDING_MODEL_NAME,
        model_kwargs={"device": config.EMBEDDING_DEVICE},
        encode_kwargs={"normalize_embeddings": config.NORMALIZE_EMBEDDINGS},
    )

    query_vector = embeddings.embed_query(QUERY_TEXT)

    client = weaviate.connect_to_local(
        host=config.WEAVIATE_HOST,
        port=config.WEAVIATE_PORT,
        grpc_port=config.WEAVIATE_GRPC_PORT,
    )

    try:
        collection = client.collections.get(args.collection)

        response = collection.query.hybrid(
            query=QUERY_TEXT,
            vector=query_vector,
            alpha=0.5,
            limit=LIMIT,
        )

        print(f"\n🔎 Query: {QUERY_TEXT}\n")

        if not response.objects:
            print("Aucun résultat.")
            return

        for i, obj in enumerate(response.objects, start=1):
            props = obj.properties
            print(f"{'=' * 80}")
            print(f"Résultat #{i}")
            print(f"Source      : {props.get('source')}")
            print(f"Loc         : {props.get('loc')}")
            print(f"Chunk index : {props.get('chunk_index')}")
            print(f"Distance    : {obj.metadata.distance}")
            print(f"Contenu     : {props.get('content', '')[:500]}")
            print()

    finally:
        client.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Vérifier le parse**

Run: `python -c "import ast; ast.parse(open('app/query_weaviate.py').read())"`
Expected: PASSE

- [ ] **Step 3: Commit**

```bash
git add app/query_weaviate.py
git commit -m "fix(query_weaviate): --collection au lieu de config.COLLECTION_NAME"
```

---

### Task 10: Git-ignore de `data/raw_src/`

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Ajouter la ligne**

Dans `.gitignore`, à côté de `/data/**/*.jsonl` :

```text
/data/raw_src/
```

- [ ] **Step 2: Vérifier**

Run: `git check-ignore data/raw_src/typescript`
Expected: renvoie le chemin (est bien ignoré)

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: ignorer data/raw_src (repos git + archives téléchargés)"
```

---

### Task 11: Smoke test de bout en bout (manuel — Weaviate requis)

**Files:**
- Aucun (vérification)

- [ ] **Step 1: Lancer l'ensemble des tests unitaires**

Run: `python -m pytest -v`
Expected: PASS (tous les tests des Tasks 1-8)

- [ ] **Step 2: Weaviate local up**

Run: `docker-compose up -d`
Expected: conteneur Weaviate démarré (port 9090)

- [ ] **Step 3: Extraire une source existante (Snowflake) pour valider la non-régression**

Run: `python app/get_docs.py --source snowflake`
Expected: reprise au dernier batch (fichiers `data/raw/snowflake_docs_batch_0NN.jsonl`), aucune erreur réseau

- [ ] **Step 4: Vérifier le sélecteur de contenu Next.js (point laissé en suspens)**

Run: `python -c "import urllib.request; html=urllib.request.urlopen('https://nextjs.org/docs/getting-started', timeout=30).read().decode('utf-8', 'ignore'); print('<article>' in html)"
Expected: si `True`, le sélecteur `"article"` est bon ; sinon ajuster `content_selector` de la source `nextjs` dans `config.py` (ex: `"[role='main']"`) et relancer les tests.

- [ ] **Step 5: Extraire TypeScript (nouvelle mécanique git) — peut prendre plusieurs minutes (clone du repo)**

Run: `python app/get_docs.py --source typescript`
Expected: des fichiers `data/raw/typescript_docs_batch_*.jsonl` sont créés ; lignes avec `source`, `loc`, `lastmod`, `content`

- [ ] **Step 6: Chunker + ingérer TypeScript**

Run: `python app/chunk_docs.py --source typescript` puis `python app/ingest_weaviate.py --source typescript`
Expected: chunks créés dans `data/chunks/typescript_chunks_batch_*.jsonl`, collection `TypeScriptDocs` créée dans Weaviate

- [ ] **Step 7: Interroger la nouvelle collection**

Run: `python app/query_weaviate.py --collection TypeScriptDocs`
Expected: des résultats de la doc TypeScript

- [ ] **Step 8: Commit final (si des ajustements ont été faits à la config)**

```bash
git add app/config/config.py
git commit -m "fix(config): sélecteur de contenu nextjs vérifié"
```

---

## Self-Review

**1. Spec coverage (CLAUDE.md → Phase A) :**
- Config data-driven `SOURCES` → Task 2 ✅
- Trois mécaniques d'extraction (`BaseExtractor` + héritage) → Tasks 3-6 ✅
- `get_docs.py` dispatcher → Task 4 ✅
- Généraliser l'extraction HTML (`content_selector`) → Task 3 + Task 2 (config) ✅
- Python via archive, TypeScript via git, Next.js via sitemap → Tasks 4-6 ✅
- Java écarté → non inclus dans `SOURCES` ✅
- Patterns de fichiers dérivés du nom → Task 2 (`docs_pattern`/`chunks_pattern`) ✅
- Chatbot UX multi-collections → **Plan séparé** `2026-09-01-chatbot-multi-collections.md` ✅ (hors périmètre de ce plan)

**2. Placeholder scan :** aucun « TBD/TODO » ; chaque étape contient le code exact. Le seul point « à vérifier » (sélecteur Next.js) est traité comme une étape explicite de vérification (Task 11 Step 4), pas un placeholder.

**3. Type consistency :** `BaseExtractor(source, raw_dir, batch_size)` est cohérent entre Tasks 3-6 ; `config.get_source`/`get_collection`/`docs_pattern`/`chunks_pattern` définis en Task 2 et consommés aux Tasks 4-8 ; `extract()` retourne `list[Path]` partout. `chunk_one_record(record, splitter=None, tokenizer=None)` défini en Task 7 et testé avec des faux — signature cohérente.
