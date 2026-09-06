"""Gestion du statut des runs d'ingestion (Phase B).

Écrit un fichier JSON par run dans data/status/, de façon atomique, plus un
pointeur latest.json. Utilisé par le runner (sous-processus) et l'app
d'administration (UI + purge).
"""

import json
import os
from datetime import datetime
from pathlib import Path

from config import config


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def run_id_from_now(now: datetime | None = None) -> str:
    """run_id lisible en nom de fichier : 2026-09-02T16-20-05."""
    base = (now or datetime.now()).isoformat(timespec="seconds")
    return base.replace(":", "-")


def status_path(status_dir, run_id: str, source: str) -> Path:
    return Path(status_dir) / f"{run_id}_{source}.json"


def read_run(path) -> dict | None:
    path = Path(path)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def create_run_file(path, *, run_id, source, operation, start_step, steps, pid=None, status_dir=None) -> dict:
    path = Path(path)
    now = _now_iso()
    record = {
        "run_id": run_id,
        "source": source,
        "operation": operation,
        "start_step": start_step,
        "steps": list(steps),
        "status": "running",
        "pid": pid,
        "created_at": now,
        "started_at": now,
        "updated_at": now,
        "finished_at": None,
        "step": None,
        "step_progress": {"done": 0, "total": None},
        "last_message": "démarrage",
        "error": None,
    }
    _atomic_write(path, record)
    if status_dir is not None:
        _set_latest(status_dir, path)
        prune_history(status_dir)
    return record


def update_run_file(path, **fields) -> dict:
    path = Path(path)
    record = read_run(path)
    if record is None:
        raise FileNotFoundError(f"fichier de statut introuvable: {path}")
    for key, value in fields.items():
        record[key] = value
    record["updated_at"] = _now_iso()
    _atomic_write(path, record)
    return record


def _refresh_latest(path: Path) -> None:
    """Rafraîchit latest.json du répertoire du run après une transition de statut."""
    _set_latest(path.parent, path)


def mark_done(path, last_message="terminé") -> dict:
    rec = update_run_file(path, status="done", finished_at=_now_iso(), last_message=last_message)
    _refresh_latest(path)
    return rec


def mark_failed(path, error) -> dict:
    rec = update_run_file(path, status="failed", finished_at=_now_iso(), error=str(error))
    _refresh_latest(path)
    return rec


def mark_cancelled(path, last_message: str = "annulé") -> dict:
    """Marque le run comme `cancelled`.

    L'appelant peut passer un `last_message` métier (par ex. "chunking 5/10
    au moment de l'arrêt") pour préserver la progression visible dans l'UI
    au lieu du libellé générique "annulé".
    """
    rec = update_run_file(path, status="cancelled", finished_at=_now_iso(), error=None, last_message=last_message)
    _refresh_latest(path)
    return rec


def _set_latest(status_dir, path: Path) -> None:
    info = read_run(path) or {}
    latest_path = Path(status_dir) / "latest.json"
    _atomic_write(latest_path, {"file": path.name, "run_id": info.get("run_id"), "updated_at": _now_iso()})


def latest_run(status_dir) -> dict | None:
    latest_path = Path(status_dir) / "latest.json"
    if not latest_path.exists():
        return None
    info = json.loads(latest_path.read_text(encoding="utf-8"))
    return read_run(Path(status_dir) / info["file"])


def list_runs(status_dir) -> list[dict]:
    status_dir = Path(status_dir)
    if not status_dir.exists():
        return []
    records = []
    for f in status_dir.glob("*.json"):
        if f.name == "latest.json":
            continue
        rec = read_run(f)
        if rec:
            records.append(rec)
    records.sort(key=lambda r: r.get("run_id", ""), reverse=True)
    return records


def prune_history(status_dir, keep: int = config.RUNS_HISTORY) -> None:
    """Supprime les plus anciens runs, en gardant les `keep` plus récents.

    On trie par `mtime` et non par nom de fichier : l'ordre lexicographique
    des `run_id` au format ISO 8601 coïncide avec l'ordre chronologique, mais
    c'est par accident. Un changement de format de `run_id` casserait la
    sémantique « garder les N plus récents » silencieusement (cf. code review H).
    """
    status_dir = Path(status_dir)
    if not status_dir.exists():
        return
    files = [f for f in status_dir.glob("*.json") if f.name != "latest.json"]
    # Plus récent d'abord.
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    for f in files[keep:]:
        f.unlink(missing_ok=True)


class RunReporter:
    """Rapporteur de progression d'une étape (utilisé par runner et scripts)."""

    def __init__(self, path):
        self.path = Path(path)

    def set_step(self, step: str) -> None:
        update_run_file(self.path, step=step, step_progress={"done": 0, "total": None})

    def progress(self, done: int, total: int | None = None) -> None:
        update_run_file(self.path, step_progress={"done": done, "total": total})

    def message(self, text: str) -> None:
        update_run_file(self.path, last_message=text)
