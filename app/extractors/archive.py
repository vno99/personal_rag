import shutil
import urllib.request
import zipfile
from pathlib import Path

from bs4 import BeautifulSoup

import config.config as config
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
        self.cache_dir = cache_dir or (Path(config.RAW_SRC_DIR) / self.name)

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
            # Timeout : si le serveur ne répond pas, on lève TimeoutError
            # au lieu de bloquer indéfiniment (cf. code review D).
            urllib.request.urlretrieve(self.archive_url, dest, timeout=60)
        return dest

    def _extract_zip(self, archive: Path) -> Path:
        extract_dir = self.cache_dir / "extracted"
        if not extract_dir.exists():
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(extract_dir)
        return extract_dir

    def _base_url(self) -> str:
        """Construit l'URL de base à partir de `archive_url`.

        Format attendu : ``https://host/path/archives/file.zip`` →
        ``https://host/path`` (le préfixe ``/archives/`` est la marque
        utilisée par la doc Python officielle).

        Pour les sources qui n'utilisent pas ce format, l'URL complète
        est retournée (et produira des `source` cassées du genre
        ``https://example.com/file.zip/page.html``). Un warning est
        loggé pour qu'une future source utilisant un format différent
        soit identifiée au moment de l'extraction plutôt qu'à l'usage
        (cf. code review Q).
        """
        if "/archives/" in self.archive_url:
            return self.archive_url.split("/archives/", 1)[0]
        logger.warning(
            "archive_url %r ne contient pas '/archives/' : le base_url "
            "retourné sera l'URL complète, ce qui peut produire des "
            "sources cassées. Adaptez _base_url si ce n'est pas le "
            "comportement souhaité.",
            self.archive_url,
        )
        return self.archive_url

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
