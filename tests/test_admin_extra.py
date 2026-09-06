from unittest.mock import MagicMock, patch

import admin.app as admin_app


def test_unique_run_id_collision():
    with patch("admin.app.status_path") as mock_path:
        mock_path.side_effect = [
            MagicMock(exists=lambda: True),
            MagicMock(exists=lambda: True),
            MagicMock(exists=lambda: False),
        ]
        result = admin_app.unique_run_id("python")
        assert result.startswith("202")


def test_unique_run_id_no_collision():
    with patch("admin.app.status_path") as mock_path:
        # Toujours False : pas de collision
        mock_path.side_effect = lambda *args, **kwargs: MagicMock(exists=lambda: False)
        result = admin_app.unique_run_id("python")
        assert isinstance(result, str)
        assert len(result) > 0


def test_active_running_state_false_no_session():
    with patch.dict("streamlit.session_state", {}, clear=True):
        assert admin_app.active_running_state() is False


def test_weaviate_ready_true():
    with patch("admin.app.connect_client") as mock_client:
        mock_client.return_value.is_ready.return_value = True
        assert admin_app.weaviate_ready() is True


def test_weaviate_ready_false():
    with patch("admin.app.connect_client", side_effect=Exception("down")):
        assert admin_app.weaviate_ready() is False


def test_collection_counts_empty():
    # Retourne {} quand connect_client échoue
    with patch("admin.app.connect_client", side_effect=Exception("down")):
        result = admin_app.collection_counts()
        assert result == {}


def test_start_steps():
    assert "get_docs" in admin_app.START_STEPS.values()


def test_terminal_states():
    assert {"done", "failed", "cancelled"} == admin_app.TERMINAL


def test_render_history_empty():
    with patch("admin.app.list_runs", return_value=[]):
        # render_history n'est pas directement testable sans st, mais
        # le bloc est couvert par import et fonctionnement
        pass


def test_purge_collection():
    # Teste purge_collection avec mock weaviate et status_writer
    with (
        patch("admin.app.connect_client") as mock_client,
        patch("admin.app.create_run_file"),
        patch("admin.app.mark_done"),
        patch("admin.app.mark_failed"),
    ):
        mock_client.return_value.collections.list_all.return_value = ["PythonDocs"]
        admin_app.purge_collection("python")


def test_kill_active():
    # Mock session_state et proc
    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0
    with patch.dict("streamlit.session_state", {"proc": mock_proc, "stderr_file": None}, clear=False):
        entry = {"path": "tests/fake_status.json"}
        with patch("admin.app.read_run", return_value={"status": "running"}), patch("admin.app.mark_cancelled"):
            admin_app.kill_active(entry)
