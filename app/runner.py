"""Orchestrateur de run d'ingestion (Phase B).

Lancé en sous-processus par l'app d'administration. Un run = un process :
il exécute séquentiellement les run() des étapes demandées (une source),
en écrivant sa progression dans data/status/{run_id}_{source}.json.
"""

import argparse
import os
import sys
from pathlib import Path

from config import config
from status_writer import (
    RunReporter,
    create_run_file,
    mark_done,
    mark_failed,
    status_path,
)

FULL_STEPS = ["get_docs", "chunk_docs", "ingest_weaviate"]


def compute_steps(operation: str, start_step: str) -> list[str]:
    """Étapes d'un run d'ingestion à partir de l'opération et du point de départ."""
    if operation != "ingest":
        raise ValueError(f"opération non gérée par le runner: {operation!r} (purge = app)")
    try:
        index = FULL_STEPS.index(start_step)
    except ValueError:
        raise ValueError(f"start_step inconnu: {start_step!r} (attendu: {FULL_STEPS})") from None
    return FULL_STEPS[index:]


def execute_run(*, run_id, source, operation, start_step, status_dir, run_funcs) -> None:
    """Exécute un run complet. Soulève en cas d'échec (après marquage failed)."""
    steps = compute_steps(operation, start_step)
    path = status_path(status_dir, run_id, source)
    create_run_file(
        path,
        run_id=run_id,
        source=source,
        operation=operation,
        start_step=start_step,
        steps=steps,
        pid=os.getpid(),
        status_dir=status_dir,
    )
    reporter = RunReporter(path)
    try:
        for step in steps:
            reporter.set_step(step)
            run_funcs[step](source, reporter)
        mark_done(path)
    except Exception as exc:
        mark_failed(path, f"{type(exc).__name__}: {exc}")
        raise


def _real_run_funcs():
    from chunk_docs import run as run_chunk
    from get_docs import run as run_get_docs
    from ingest_weaviate import run as run_ingest

    return {"get_docs": run_get_docs, "chunk_docs": run_chunk, "ingest_weaviate": run_ingest}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Exécute un run d'ingestion pour une source.")
    parser.add_argument("--source", required=True, choices=[s["name"] for s in config.SOURCES], help="Source à ingérer")
    parser.add_argument("--run-id", required=True, help="Identifiant du run, ex. 2026-09-02T16-20-05")
    parser.add_argument("--operation", default="ingest", choices=["ingest"])
    parser.add_argument("--start-step", default="get_docs", choices=FULL_STEPS)
    args = parser.parse_args(argv)
    try:
        execute_run(
            run_id=args.run_id,
            source=args.source,
            operation=args.operation,
            start_step=args.start_step,
            status_dir=Path(config.STATUS_DIR),
            run_funcs=_real_run_funcs(),
        )
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
