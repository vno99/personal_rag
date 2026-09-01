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
