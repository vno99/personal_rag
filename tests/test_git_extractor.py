import subprocess
from pathlib import Path

from extractors.git import GitExtractor


def make_local_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "master", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@test.com"], check=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test"], check=True
    )
    (repo / "docs").mkdir()
    (repo / "docs" / "intro.md").write_text("# Intro\nTexte d'intro.", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True
    )
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
    assert record["loc"] == "docs/intro.md"
    assert "# Intro" in record["content"]
    assert record["lastmod"] is not None
