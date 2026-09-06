"""Tests de couverture supplémentaires pour app/extractors/git.py."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from extractors.git import GitExtractor


class TestGitExtractorCloneOrFetch:
    """Tests pour _clone_or_fetch."""

    def test_clone_or_fetch_fresh_clone(self, tmp_path):
        """Repo sans .git → git clone appelé."""
        source = {
            "name": "typescript",
            "type": "git",
            "repo_url": "https://github.com/microsoft/TypeScript-Website.git",
            "branch": "v2",
            "docs_path": "packages/documentation/copy/en",
            "collection": "TypeScriptDocs",
            "content_selector": None,
        }
        cache = tmp_path / "cache"
        raw = tmp_path / "raw"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            extractor = GitExtractor(source, raw, batch_size=500, cache_dir=cache)
            # Mock repo n'a pas .git → clone
            extractor._clone_or_fetch()
            # subprocess.run appelé 1 fois (clone)
            assert mock_run.call_count == 1
            args = mock_run.call_args[0][0]
            assert "clone" in args

    def test_clone_or_fetch_fast_forward(self, tmp_path):
        """Repo avec .git → git fetch origin branch:branch."""
        source = {
            "name": "typescript",
            "type": "git",
            "repo_url": "https://github.com/microsoft/TypeScript-Website.git",
            "branch": "v2",
            "docs_path": "packages/documentation/copy/en",
            "collection": "TypeScriptDocs",
            "content_selector": None,
        }
        cache = tmp_path / "cache"
        cache.mkdir(parents=True)
        (cache / ".git").touch()  # Simule un repo git
        raw = tmp_path / "raw"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            extractor = GitExtractor(source, raw, batch_size=500, cache_dir=cache)
            extractor._clone_or_fetch()
            # subprocess.run appelé 1 fois (fetch)
            assert mock_run.call_count == 1
            args = mock_run.call_args[0][0]
            assert "fetch" in args


class TestGitExtractorLastModified:
    """Tests pour _last_modified."""

    def test_last_modified_returns_iso8601(self, tmp_path):
        """_last_modified retourne le format ISO 8601 de git log."""
        source = {
            "name": "typescript",
            "type": "git",
            "repo_url": "https://github.com/microsoft/TypeScript-Website.git",
            "branch": "v2",
            "docs_path": "docs",
            "collection": "TypeScriptDocs",
            "content_selector": None,
        }
        cache = tmp_path / "cache"
        raw = tmp_path / "raw"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="2026-09-07T10:30:00+00:00", strip=MagicMock(return_value="2026-09-07T10:30:00+00:00")
            )
            extractor = GitExtractor(source, raw, batch_size=500, cache_dir=cache)
            result = extractor._last_modified(Path("docs/intro.md"))
            # Doit retourner une string non-vide
            assert result is not None

    def test_last_modified_empty_output(self, tmp_path):
        """_last_modified retourne None si git log retourne vide."""
        source = {
            "name": "typescript",
            "type": "git",
            "repo_url": "https://github.com/microsoft/TypeScript-Website.git",
            "branch": "v2",
            "docs_path": "docs",
            "collection": "TypeScriptDocs",
            "content_selector": None,
        }
        cache = tmp_path / "cache"
        raw = tmp_path / "raw"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", strip=MagicMock(return_value=""))
            extractor = GitExtractor(source, raw, batch_size=500, cache_dir=cache)
            result = extractor._last_modified(Path("docs/intro.md"))
            assert result is None


class TestGitExtractorBlobUrl:
    """Tests pour _blob_url."""

    def test_blob_url_https(self, tmp_path):
        """_blob_url construit une URL HTTPS valide."""
        source = {
            "name": "typescript",
            "type": "git",
            "repo_url": "https://github.com/microsoft/TypeScript-Website.git",
            "branch": "v2",
            "docs_path": "docs",
            "collection": "TypeScriptDocs",
            "content_selector": None,
        }
        extractor = GitExtractor(source, tmp_path / "raw", cache_dir=tmp_path / "cache")
        url = extractor._blob_url(Path("docs/intro.md"))
        assert url.startswith("https://")
        assert "/blob/" in url

    def test_blob_url_local_repo(self, tmp_path):
        """_blob_url pour depot local → file:// URL."""
        source = {
            "name": "typescript",
            "type": "git",
            "repo_url": "/local/path/repo.git",  # pas http/https
            "branch": "v2",
            "docs_path": "docs",
            "collection": "TypeScriptDocs",
            "content_selector": None,
        }
        extractor = GitExtractor(source, tmp_path / "raw", cache_dir=tmp_path / "cache")
        url = extractor._blob_url(Path("docs/intro.md"))
        assert url.startswith("file://")


class TestGitExtractorExtract:
    """Tests pour extract()."""

    def test_extract_progress_callback(self, tmp_path):
        """extract() appelle le callback progress si fourni."""
        source = {
            "name": "typescript",
            "type": "git",
            "repo_url": str(tmp_path / "repo"),
            "branch": "master",
            "docs_path": "docs",
            "collection": "TypeScriptDocs",
            "content_selector": None,
        }
        # Créer un vrai repo git local pour le test
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "master"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
        docs = repo / "docs"
        docs.mkdir()
        (docs / "intro.md").write_text("# Intro\nTest content.", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True)

        extractor = GitExtractor(source, tmp_path / "raw", batch_size=500, cache_dir=tmp_path / "src")
        mock_progress = MagicMock()
        written = extractor.extract(progress=mock_progress)
        assert len(written) == 1
        # Progress appelé pour chaque fichier (1)
        assert mock_progress.call_count == 1

    def test_extract_multiple_batches(self, tmp_path):
        """extract() crée plusieurs batches quand batch_size dépassé."""
        source = {
            "name": "typescript",
            "type": "git",
            "repo_url": str(tmp_path / "repo"),
            "branch": "master",
            "docs_path": "docs",
            "collection": "TypeScriptDocs",
            "content_selector": None,
        }
        # Créer un vrai repo avec plusieurs fichiers
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "master"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
        docs = repo / "docs"
        docs.mkdir()
        for i in range(3):
            (docs / f"doc{i}.md").write_text(f"# Doc {i}\nContent.", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True)

        extractor = GitExtractor(source, tmp_path / "raw", batch_size=2, cache_dir=tmp_path / "src")
        written = extractor.extract()
        # 3 fichiers, batch_size=2 → 2 batches
        assert len(written) == 2
