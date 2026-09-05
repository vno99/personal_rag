import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from config.config import docs_pattern

__all__ = ["BaseExtractor", "ProgressCallback"]

ProgressCallback = Callable[[int, int | None], None]


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
    def extract(self, progress: ProgressCallback | None = None) -> list[Path]:
        """Extrait les documents et écrit les fichiers JSONL bruts.

        Args:
            progress: callback optionnel appelé avec (done, total) au fil de
                l'extraction ; `total` vaut None quand il est inconnu d'avance.

        Returns:
            list[Path]: Les chemins des fichiers batch écrits.
        """
        raise NotImplementedError
