import subprocess
from pathlib import Path
from urllib.parse import urlparse

import config.config as config
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
        self.cache_dir = cache_dir or (Path(config.RAW_SRC_DIR) / self.name)

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
            path = parsed.path.rstrip("/").removesuffix(".git")
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
