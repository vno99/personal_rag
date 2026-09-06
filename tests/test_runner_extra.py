import pytest
from runner import compute_steps, execute_run, main


def test_compute_steps_unknown_start():
    with pytest.raises(ValueError, match="start_step inconnu"):
        compute_steps("ingest", "inconnu")


def test_main_success(monkeypatch, tmp_path):
    # Couvre lignes 70-87 (main) et 91
    monkeypatch.setattr("sys.argv", ["runner", "--source", "python", "--run-id", "test-run"])
    # On mock _real_run_funcs pour éviter d'importer les vrais modules
    import runner

    monkeypatch.setattr(
        runner,
        "_real_run_funcs",
        lambda: {
            "get_docs": lambda s, st: st.message("ok"),
            "chunk_docs": lambda s, st: None,
            "ingest_weaviate": lambda s, st: None,
        },
    )
    assert main(["--source", "python", "--run-id", "test-run", "--start-step", "get_docs"]) == 0


def test_execute_run_with_operation_ingest(tmp_path):
    # Couvre lignes 31-32 et 62-66
    def ok(s, st):
        st.message("ok")

    funcs = {"get_docs": ok, "chunk_docs": ok, "ingest_weaviate": ok}
    execute_run(
        run_id="test",
        source="python",
        operation="ingest",
        start_step="get_docs",
        status_dir=tmp_path,
        run_funcs=funcs,
    )
