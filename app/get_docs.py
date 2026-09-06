import argparse
from pathlib import Path

from config import config
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
