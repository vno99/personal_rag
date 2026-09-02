import pytest

from runner import compute_steps, execute_run
from status_writer import read_run, status_path


def test_compute_steps_full():
    assert compute_steps("ingest", "get_docs") == ["get_docs", "chunk_docs", "ingest_weaviate"]


def test_compute_steps_advanced_starts():
    assert compute_steps("ingest", "chunk_docs") == ["chunk_docs", "ingest_weaviate"]
    assert compute_steps("ingest", "ingest_weaviate") == ["ingest_weaviate"]


def test_compute_steps_rejects_purge():
    with pytest.raises(ValueError):
        compute_steps("purge", "get_docs")


def test_execute_run_success_writes_done(tmp_path):
    calls = []

    def make(step):
        def run(source, status):
            calls.append(step)
            status.progress(1, 1)
        return run

    funcs = {"get_docs": make("get_docs"), "chunk_docs": make("chunk_docs"),
             "ingest_weaviate": make("ingest_weaviate")}
    execute_run(run_id="2026-09-02T10-00-00", source="python", operation="ingest",
                start_step="chunk_docs", status_dir=tmp_path, run_funcs=funcs)
    assert calls == ["chunk_docs", "ingest_weaviate"]
    rec = read_run(status_path(tmp_path, "2026-09-02T10-00-00", "python"))
    assert rec["status"] == "done"
    assert rec["step_progress"] == {"done": 1, "total": 1}
    assert rec["pid"] is not None


def test_execute_run_failure_marks_failed_and_stops(tmp_path):
    def boom(source, status):
        raise RuntimeError("explose")

    funcs = {"get_docs": boom, "chunk_docs": lambda s, st: None,
             "ingest_weaviate": lambda s, st: None}
    with pytest.raises(RuntimeError):
        execute_run(run_id="2026-09-02T10-00-01", source="python", operation="ingest",
                    start_step="get_docs", status_dir=tmp_path, run_funcs=funcs)
    rec = read_run(status_path(tmp_path, "2026-09-02T10-00-01", "python"))
    assert rec["status"] == "failed"
    assert "explose" in rec["error"]
