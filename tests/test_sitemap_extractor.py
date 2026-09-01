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
        blocknum = kwargs.get("blocknum", 0)

        # Le SitemapLoader réel lève une ValueError dans load() quand blocknum
        # dépasse le dernier bloc : on émule ce comportement pour terminer la boucle.
        class BlockedLoader(FakeLoader):
            def load(self):
                if blocknum > 1:
                    raise ValueError("Selected sitemap does not contain enough blocks for given blocknum")
                return self._docs

        return BlockedLoader([FakeDoc("nouveau", "https://x.com/new", "new", "2026-02-01")])

    source = {
        "name": "nextjs", "type": "sitemap",
        "sitemap_url": "https://nextjs.org/sitemap.xml",
        "filter_urls": [r"https://nextjs\.org/docs/.*"],
        "collection": "NextJSDocs", "content_selector": "article",
    }
    extractor = SitemapExtractor(source, tmp_path, batch_size=500, loader_factory=loader_factory)
    written = extractor.extract()

    assert len(written) == 1
    assert written[0].name == "nextjs_docs_batch_001.jsonl"
