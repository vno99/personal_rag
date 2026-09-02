from status_writer import (
    create_run_file, latest_run, list_runs, mark_cancelled, mark_done,
    mark_failed, prune_history, read_run, run_id_from_now, status_path,
    update_run_file,
)


def test_run_id_from_now_has_no_colons():
    rid = run_id_from_now()
    assert ":" not in rid


def test_create_and_read(tmp_path):
    path = status_path(tmp_path, "2026-09-02T16-20-05", "python")
    create_run_file(path, run_id="2026-09-02T16-20-05", source="python", operation="ingest",
                    start_step="chunk_docs", steps=["chunk_docs", "ingest_weaviate"],
                    pid=123, status_dir=tmp_path)
    rec = read_run(path)
    assert rec["status"] == "running"
    assert rec["source"] == "python"
    assert rec["steps"] == ["chunk_docs", "ingest_weaviate"]
    assert rec["pid"] == 123
    assert rec["step"] is None


def test_atomic_write_leaves_no_tmp(tmp_path):
    path = status_path(tmp_path, "r1", "python")
    create_run_file(path, run_id="r1", source="python", operation="ingest",
                    start_step="get_docs", steps=["get_docs"])
    assert not list(tmp_path.glob("*.tmp"))


def test_transitions(tmp_path):
    path = status_path(tmp_path, "r1", "python")
    create_run_file(path, run_id="r1", source="python", operation="ingest",
                    start_step="get_docs", steps=["get_docs"], status_dir=tmp_path)
    mark_done(path)
    rec = read_run(path)
    assert rec["status"] == "done" and rec["finished_at"] is not None
    mark_failed(path, "boom")
    assert read_run(path)["status"] == "failed"
    assert read_run(path)["error"] == "boom"
    mark_cancelled(path)
    rec = read_run(path)
    assert rec["status"] == "cancelled" and rec["error"] is None


def test_update_progress_and_step(tmp_path):
    path = status_path(tmp_path, "r1", "python")
    create_run_file(path, run_id="r1", source="python", operation="ingest",
                    start_step="chunk_docs", steps=["chunk_docs"], status_dir=tmp_path)
    update_run_file(path, step="chunk_docs", step_progress={"done": 2, "total": 5})
    rec = read_run(path)
    assert rec["step"] == "chunk_docs"
    assert rec["step_progress"] == {"done": 2, "total": 5}


def test_latest_and_prune(tmp_path):
    for rid in ["2026-09-02T16-00-00", "2026-09-02T17-00-00", "2026-09-02T18-00-00"]:
        create_run_file(status_path(tmp_path, rid, "python"), run_id=rid, source="python",
                        operation="ingest", start_step="get_docs", steps=["get_docs"],
                        status_dir=tmp_path)
    runs = list_runs(tmp_path)
    assert [r["run_id"] for r in runs] == [
        "2026-09-02T18-00-00", "2026-09-02T17-00-00", "2026-09-02T16-00-00"]
    assert latest_run(tmp_path)["run_id"] == "2026-09-02T18-00-00"
    prune_history(tmp_path, keep=2)
    left = sorted(p.name for p in tmp_path.glob("*.json") if p.name != "latest.json")
    assert left == ["2026-09-02T17-00-00_python.json", "2026-09-02T18-00-00_python.json"]
    assert (tmp_path / "latest.json").exists()
