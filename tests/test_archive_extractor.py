# tests/test_archive_extractor.py
import shutil
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


def test_archive_extractor_parses_html(tmp_path, monkeypatch):
    archive = make_local_zip(tmp_path)

    # Évite le téléchargement réseau : on redirige urlretrieve vers le zip local.
    def fake_urlretrieve(url: str, dest: str | Path, timeout: int | None = None):
        shutil.copyfile(archive, dest)

    monkeypatch.setattr("urllib.request.urlretrieve", fake_urlretrieve)

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


def test_archive_extractor_reports_progress(tmp_path, monkeypatch):
    archive = make_local_zip(tmp_path)

    def fake_urlretrieve(url: str, dest, timeout: int | None = None):
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
