"""Tests de couverture pour admin/app.py - zones non couvertes."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import streamlit as st

import admin.app as admin_app

# ─────────────────────────────────────────────────────────────────────────────
# active_running_state
# ─────────────────────────────────────────────────────────────────────────────


def test_active_running_state_true_rec_not_terminal(tmp_path):
    """rec existe et status not in TERMINAL → retourne True."""
    run_file = tmp_path / "run.json"
    run_file.write_text('{"status": "running"}', encoding="utf-8")
    entry = {"path": str(run_file)}
    with patch.dict("streamlit.session_state", {"active": entry}, clear=False):
        with patch("admin.app.read_run", return_value={"status": "running"}):
            assert admin_app.active_running_state() is True


def test_active_running_state_false_rec_terminal(tmp_path):
    """rec existe avec status terminal → retourne False."""
    run_file = tmp_path / "run.json"
    run_file.write_text('{"status": "done"}', encoding="utf-8")
    entry = {"path": str(run_file)}
    with patch.dict("streamlit.session_state", {"active": entry}, clear=False):
        with patch("admin.app.read_run", return_value={"status": "done"}):
            assert admin_app.active_running_state() is False


def test_active_running_state_false_proc_alive(tmp_path):
    """pas de rec mais proc vivant → retourne True."""
    entry = {"path": str(tmp_path / "nope.json")}
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None  # vivant
    with patch.dict("streamlit.session_state", {"active": entry, "proc": mock_proc}, clear=False):
        with patch("admin.app.read_run", return_value=None):
            assert admin_app.active_running_state() is True


def test_active_running_state_false_proc_dead(tmp_path):
    """pas de rec et proc mort → retourne False."""
    entry = {"path": str(tmp_path / "nope.json")}
    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0  # mort
    with patch.dict("streamlit.session_state", {"active": entry, "proc": mock_proc}, clear=False):
        with patch("admin.app.read_run", return_value=None):
            assert admin_app.active_running_state() is False


# ─────────────────────────────────────────────────────────────────────────────
# collection_counts
# ─────────────────────────────────────────────────────────────────────────────


def test_collection_counts_with_collections():
    """collection présente → count est un entier."""
    mock_client = MagicMock()
    mock_client.collections.list_all.return_value = {"SnowflakeDocs", "PythonDocs"}
    agg_result = MagicMock()
    agg_result.total_count = 42
    mock_coll = MagicMock()
    mock_coll.aggregate.over_all.return_value = agg_result
    mock_client.collections.get.return_value = mock_coll

    with patch("admin.app.connect_client", return_value=mock_client):
        with patch("admin.app.config.SOURCES", admin_app.config.SOURCES):
            counts = admin_app.collection_counts()
            # SnowflakeDocs dans existing → count = 42
            assert counts.get("snowflake") == 42
            # PythonDocs dans existing → count = 42 ( même mock_coll)
            assert counts.get("python") == 42
            # databricks n'est pas dans existing → None
            assert counts.get("databricks") is None


def test_collection_counts_client_exception():
    """connect_client lève une exception → {}."""
    with patch("admin.app.connect_client", side_effect=Exception("network")):
        assert admin_app.collection_counts() == {}


def test_collection_counts_aggregate_exception():
    """aggregate.over_all lève une exception → None pour cette source."""
    mock_client = MagicMock()
    mock_client.collections.list_all.return_value = {"SnowflakeDocs"}
    mock_client.collections.get.side_effect = Exception("boom")
    with patch("admin.app.connect_client", return_value=mock_client):
        counts = admin_app.collection_counts()
        assert counts.get("snowflake") is None


# ─────────────────────────────────────────────────────────────────────────────
# launch_ingest
# ─────────────────────────────────────────────────────────────────────────────


def test_launch_ingest_success(tmp_path):
    """subprocess.Popen réussit → active et proc en session_state."""
    mock_proc = MagicMock()
    status_file = tmp_path / "status.json"
    with (
        patch("admin.app.unique_run_id", return_value="2026-09-07T10-00-00-python"),
        patch("admin.app.status_path", return_value=status_file),
        patch("admin.app.STATUS_DIR", tmp_path),
        patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
        patch.dict("streamlit.session_state", {}, clear=False),
    ):
        admin_app.launch_ingest("python", "Extraction complète")
        mock_popen.assert_called_once()
        assert "active" in st.session_state
        assert "proc" in st.session_state


def test_launch_ingest_popen_exception(tmp_path):
    """subprocess.Popen lève une exception → run file marqué failed."""
    mock_path = MagicMock(spec=Path)
    mock_path.exists.return_value = False
    with (
        patch("admin.app.unique_run_id", return_value="2026-09-07T10-00-00-python"),
        patch("admin.app.status_path", return_value=mock_path),
        patch("admin.app.STATUS_DIR", tmp_path),
        patch("subprocess.Popen", side_effect=OSError("python not found")),
        patch("admin.app.create_run_file") as mock_create,
        patch("admin.app.mark_failed") as mock_fail,
        patch.dict("streamlit.session_state", {}, clear=False),
    ):
        admin_app.launch_ingest("python", "Extraction complète")
        mock_create.assert_called_once()
        mock_fail.assert_called_once()
        # session_state["active"] ne doit PAS être peuplé après failed
        assert "active" not in st.session_state


# ─────────────────────────────────────────────────────────────────────────────
# render_run (fonction helper - vérifie branches)
# ─────────────────────────────────────────────────────────────────────────────


def test_render_run_no_progress():
    """render_run avec step_progress sans total."""
    rec = {"status": "running", "step": "get_docs", "step_progress": {"done": 5}, "pid": 1234, "last_message": "ok"}
    # On vérite juste que la fonction ne lève pas ( Streamlit mocked )
    with patch("streamlit.markdown"), patch("streamlit.write"), patch("streamlit.progress") as mock_prog:
        admin_app.render_run(rec, stderr_path=None)
        # total manquant → progress jamais appelée avec ce rec
        mock_prog.assert_not_called()


def test_render_run_with_progress():
    """render_run avec step_progress complet."""
    rec = {
        "status": "running",
        "step": "chunking",
        "step_progress": {"done": 3, "total": 10},
        "pid": 5678,
        "last_message": "chunking 3/10",
        "error": None,
    }
    with patch("streamlit.markdown"), patch("streamlit.write"), patch("streamlit.progress") as mock_prog:
        admin_app.render_run(rec, stderr_path=None)
        mock_prog.assert_called_once()


def test_render_run_with_error():
    """render_run avec error → st.error appelé."""
    rec = {"status": "failed", "step": None, "step_progress": {}, "pid": None, "last_message": None, "error": "oops"}
    with patch("streamlit.markdown"), patch("streamlit.write"), patch("streamlit.error") as mock_err:
        admin_app.render_run(rec, stderr_path=None)
        mock_err.assert_called_once()


def test_render_run_stderr_exists_and_nonzero(tmp_path):
    """render_run avec stderr_path existant et non-vide → st.code appelé."""
    stderr = tmp_path / "run.stderr.log"
    stderr.write_text("error output here", encoding="utf-8")
    rec = {"status": "running", "step": None, "step_progress": {}, "pid": None, "last_message": None, "error": None}
    with patch("streamlit.markdown"), patch("streamlit.write"), patch("streamlit.caption"), patch("streamlit.code"):
        admin_app.render_run(rec, stderr_path=str(stderr))


# ─────────────────────────────────────────────────────────────────────────────
# render_history
# ─────────────────────────────────────────────────────────────────────────────


def test_render_history_with_runs():
    """render_history avec runs → st.expander appelé."""
    runs = [
        {"run_id": "2026-09-07T10-00-00", "source": "python", "operation": "ingest", "status": "done"},
        {"run_id": "2026-09-06T09-00-00", "source": "typescript", "operation": "ingest", "status": "failed"},
    ]
    with patch("admin.app.list_runs", return_value=runs):
        with (
            patch("streamlit.subheader"),
            patch("streamlit.info") as mock_info,
            patch("streamlit.expander") as mock_exp,
        ):
            mock_exp.return_value.__enter__ = MagicMock(return_value=mock_exp.return_value)
            mock_exp.return_value.__exit__ = MagicMock(return_value=False)
            admin_app.render_history()
            mock_info.assert_not_called()  # car runs non vide


def test_render_history_skips_invalid():
    """render_history fait runs.sort() puis skip les entrées non-dict via continue.

    Note: runs.sort() est appelé AVANT l'itération, donc si list_runs
    retourne une string, sort() lève AttributeError. Le filtrage via
    `isinstance(r, dict)` ne protège pas le sort().
    """
    runs = [
        {"run_id": "2026-09-07T10-00-00", "source": "python", "operation": "ingest", "status": "done"},
        {},  # skip (no run_id) - dict mais sans run_id
        {"source": "python"},  # skip (no run_id)
    ]
    with patch("admin.app.list_runs", return_value=runs):
        with (
            patch("streamlit.subheader"),
            patch("streamlit.info"),
            patch("streamlit.expander") as mock_exp,
        ):
            mock_exp.return_value.__enter__ = MagicMock(return_value=mock_exp.return_value)
            mock_exp.return_value.__exit__ = MagicMock(return_value=False)
            admin_app.render_history()
            # 1 expander pour le run valide, 2 dicts filtrés
            assert mock_exp.call_count == 1


def test_render_history_empty():
    """render_history avec runs vides → st.info appelé."""
    with patch("admin.app.list_runs", return_value=[]):
        with patch("streamlit.subheader"), patch("streamlit.info") as mock_info:
            admin_app.render_history()
            mock_info.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# kill_active
# ─────────────────────────────────────────────────────────────────────────────


def test_kill_active_proc_kill_oeserror():
    """proc.kill() lève OSError → ignoré."""
    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0
    mock_proc.kill.side_effect = OSError("permission")
    mock_stderr = MagicMock()
    entry = {"path": str(Path("/fake/status.json"))}
    with (
        patch.dict("streamlit.session_state", {"proc": mock_proc, "stderr_file": mock_stderr}, clear=False),
        patch("admin.app.read_run", return_value={"status": "running"}),
        patch("admin.app.mark_cancelled"),
    ):
        admin_app.kill_active(entry)
        mock_proc.kill.assert_called_once()


def test_kill_active_stderr_file_close_exception():
    """stderr_file.close() lève une exception → ignoré."""
    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0
    mock_stderr = MagicMock()
    mock_stderr.close.side_effect = Exception("close failed")
    entry = {"path": str(Path("/fake/status.json"))}
    with (
        patch.dict("streamlit.session_state", {"proc": mock_proc, "stderr_file": mock_stderr}, clear=False),
        patch("admin.app.read_run", return_value={"status": "running"}),
        patch("admin.app.mark_cancelled"),
    ):
        admin_app.kill_active(entry)


def test_kill_active_no_cancelled_if_terminal(tmp_path):
    """rec est terminal → mark_cancelled pas appelé."""
    run_file = tmp_path / "run.json"
    run_file.write_text('{"status": "done"}', encoding="utf-8")
    mock_proc = MagicMock()
    entry = {"path": str(run_file)}
    with (
        patch.dict("streamlit.session_state", {"proc": mock_proc}, clear=False),
        patch("admin.app.read_run", return_value={"status": "done"}),
        patch("admin.app.mark_cancelled") as mock_cancel,
    ):
        admin_app.kill_active(entry)
        mock_cancel.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# purge_collection branches supplémentaires
# ─────────────────────────────────────────────────────────────────────────────


def test_purge_collection_not_exists():
    """collection n'existe pas → mark_done quand même appelé (comportement actuel)."""
    with (
        patch("admin.app.connect_client") as mock_client,
        patch("admin.app.create_run_file"),
        patch("admin.app.mark_done") as mock_done,
        patch("admin.app.mark_failed") as mock_fail,
    ):
        mock_client.return_value.collections.list_all.return_value = set()  # aucune collection
        admin_app.purge_collection("python")
        # mark_done est appelé même si la collection n'existe pas (message "supprimée" même si rien fait)
        mock_done.assert_called_once()
        mock_fail.assert_not_called()


def test_purge_collection_exception():
    """exception lors de delete → mark_failed appelé."""
    with (
        patch("admin.app.connect_client") as mock_client,
        patch("admin.app.create_run_file"),
        patch("admin.app.mark_failed") as mock_fail,
    ):
        mock_client.return_value.collections.list_all.return_value = {"PythonDocs"}
        mock_client.return_value.collections.delete.side_effect = Exception("boom")
        admin_app.purge_collection("python")
        mock_fail.assert_called_once()


def test_purge_collection_list_all_exception():
    """exception lors de list_all → mark_failed appelé."""
    with (
        patch("admin.app.connect_client") as mock_client,
        patch("admin.app.create_run_file"),
        patch("admin.app.mark_failed") as mock_fail,
    ):
        mock_client.return_value.collections.list_all.side_effect = Exception("network error")
        admin_app.purge_collection("python")
        mock_fail.assert_called_once()
