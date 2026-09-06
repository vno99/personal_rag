"""Tests de couverture pour app/get_docs.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from get_docs import EXTRACTORS, run


class TestRun:
    """Tests pour la fonction `run` (progress callback)."""

    def test_run_calls_extractor_extract_with_progress(self):
        """run() appelle extractor.extract(progress=...) et log le bon message."""
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = [Path("/fake/batch1.jsonl"), Path("/fake/batch2.jsonl")]

        mock_cls = MagicMock(return_value=mock_extractor)
        with patch.dict(EXTRACTORS, {"sitemap": mock_cls}):
            with patch("get_docs.config.get_source", return_value={"name": "snowflake", "type": "sitemap"}):
                with patch("get_docs.logger") as mock_logger:
                    run("snowflake")

        mock_cls.assert_called_once()
        mock_extractor.extract.assert_called_once()
        # logger.info appelé 2 fois (début + fin)
        assert mock_logger.info.call_count == 2

    def test_run_with_status_callback(self):
        """run(source, status) → callback progress est passé à extract."""
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = []
        mock_cls = MagicMock(return_value=mock_extractor)

        mock_status = MagicMock()

        with patch.dict(EXTRACTORS, {"sitemap": mock_cls}):
            with patch("get_docs.config.get_source", return_value={"name": "snowflake", "type": "sitemap"}):
                with patch("get_docs.logger"):
                    run("snowflake", status=mock_status)

        # extract a été appelé avec progress callback
        call_kwargs = mock_extractor.extract.call_args.kwargs
        assert "progress" in call_kwargs
        # le callback appelle status.progress
        call_kwargs["progress"](5, 10)
        mock_status.progress.assert_called_once_with(5, 10)


class TestMain:
    """Tests pour la fonction `main` (CLI argparse)."""

    def test_main_parses_source_argument(self):
        """main() reject si --source manquant."""
        with patch("sys.argv", ["get_docs.py"]):
            with pytest.raises(SystemExit):
                from get_docs import main

                main()

    def test_main_parses_invalid_source(self):
        """main() reject source invalide."""
        with patch("sys.argv", ["get_docs.py", "--source", "invalid_source"]):
            with pytest.raises(SystemExit):
                from get_docs import main

                main()
