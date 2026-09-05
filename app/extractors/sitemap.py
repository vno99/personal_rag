from pathlib import Path

from bs4 import BeautifulSoup
from langchain_community.document_loaders.sitemap import SitemapLoader

import config.config as config

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
                "User-Agent": config.USER_AGENT,
            },
            "timeout": 30,
        }
        return loader

    def extract(self, progress=None) -> list[Path]:
        written: list[Path] = []
        blocknum = self._find_next_batch_num()
        done = 0
        # Garde-fou : on borne le nombre de blocs au cas où SitemapLoader
        # changerait son message d'erreur ou ne lèverait plus. 10000 blocs *
        # batch_size 500 = 5M docs, largement au-dessus de ce qu'on ingère
        # réellement (cf. code review C).
        max_blocks = 10000

        while blocknum < max_blocks:
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
