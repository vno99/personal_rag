"""App d'administration du pipeline RAG (Phase B).

Lance les runs d'ingestion en sous-processus (app/runner.py), affiche leur
statut temps réel (data/status/*.json), permet de les arrêter, purge une
collection Weaviate et garde un historique borné.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "app"))

import config.config as config  # noqa: E402
from status_writer import (  # noqa: E402
    create_run_file, list_runs, mark_cancelled, mark_done, mark_failed,
    read_run, run_id_from_now, status_path,
)

STATUS_DIR = Path(config.STATUS_DIR)

START_STEPS = {
    "Extraction complète": "get_docs",
    "Dès le chunking (raw existants)": "chunk_docs",
    "Dès l'ingestion (chunks existants)": "ingest_weaviate",
}
TERMINAL = {"done", "failed", "cancelled"}

SOURCE_CHOICES = [s["name"] for s in config.SOURCES]


def unique_run_id(source: str) -> str:
    """run_id unique pour la source : suffixe -2, -3, … en cas de collision (même seconde)."""
    base = run_id_from_now()
    run_id = base
    n = 2
    while status_path(STATUS_DIR, run_id, source).exists():
        run_id = f"{base}-{n}"
        n += 1
    return run_id


def active_running_state() -> bool:
    """Un run non terminal est-il en cours (fichier présent ou process vivant) ?"""
    entry = st.session_state.get("active")
    if not entry:
        return False
    rec = read_run(Path(entry["path"]))
    if rec is not None:
        return rec.get("status") not in TERMINAL
    proc = st.session_state.get("proc")
    return proc is not None and proc.poll() is None


def weaviate_ready() -> bool:
    try:
        return bool(connect_client().is_ready())
    except Exception:
        return False


@st.cache_resource
def connect_client():
    import weaviate
    return weaviate.connect_to_local(
        host=config.WEAVIATE_HOST, port=config.WEAVIATE_PORT,
        grpc_port=config.WEAVIATE_GRPC_PORT,
    )


def collection_counts() -> dict[str, int | None]:
    """{nom_source: nb_objets | None si collection absente}."""
    counts = {}
    try:
        client = connect_client()
        existing = set(client.collections.list_all())
    except Exception:
        return {}
    for src in config.SOURCES:
        name = src["collection"]
        try:
            if name in existing:
                counts[src["name"]] = client.collections.get(name).aggregate.over_all(
                    total_count=True).total_count
            else:
                counts[src["name"]] = None
        except Exception:
            counts[src["name"]] = None
    return counts


def launch_ingest(source: str, label: str) -> None:
    start_step = START_STEPS[label]
    run_id = unique_run_id(source)
    path = status_path(STATUS_DIR, run_id, source)
    cmd = [
        sys.executable, "app/runner.py",
        "--source", source, "--run-id", run_id,
        "--operation", "ingest", "--start-step", start_step,
    ]
    proc = None
    try:
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:  # ex. python introuvable : on trace un run failed
        STATUS_DIR.mkdir(parents=True, exist_ok=True)
        create_run_file(path, run_id=run_id, source=source, operation="ingest",
                        start_step=start_step,
                        steps=[start_step], status_dir=STATUS_DIR)
        mark_failed(path, f"impossible de lancer le runner: {exc}")
    st.session_state["active"] = {"run_id": run_id, "source": source,
                                  "label": label, "path": str(path)}
    st.session_state["proc"] = proc


def purge_collection(source: str) -> None:
    collection = config.get_collection(source)
    run_id = unique_run_id(source)
    path = status_path(STATUS_DIR, run_id, source)
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    create_run_file(path, run_id=run_id, source=source, operation="purge",
                    start_step="purge", steps=["purge"], status_dir=STATUS_DIR)
    try:
        client = connect_client()
        existing = set(client.collections.list_all())
        if collection in existing:
            client.collections.delete(collection)
        mark_done(path, last_message=f"Collection {collection} supprimée")
    except Exception as exc:
        mark_failed(path, str(exc))
    st.session_state.pop("active", None)
    st.session_state.pop("proc", None)
    st.session_state["confirm_purge"] = False


def kill_active(entry: dict) -> None:
    proc = st.session_state.get("proc")
    if proc is not None:
        try:
            proc.kill()
        except OSError:
            pass
    path = Path(entry["path"])
    rec = read_run(path)
    if rec is not None and rec.get("status") not in TERMINAL:
        mark_cancelled(path)
    st.session_state.pop("active", None)
    st.session_state.pop("proc", None)


def render_run(rec: dict) -> None:
    st.markdown(f"**Statut :** `{rec.get('status')}` — étape : `{rec.get('step') or '—'}`")
    prog = rec.get("step_progress") or {}
    done, total = prog.get("done", 0), prog.get("total")
    if total:
        st.progress(min(done / total, 1.0), text=f"{done}/{total}")
    st.write(f"PID : `{rec.get('pid')}` — {rec.get('last_message') or ''}")
    if rec.get("error"):
        st.error(rec["error"])


def render_history() -> None:
    runs = list_runs(STATUS_DIR)
    if not runs:
        st.info("Aucun run pour l'instant.")
        return
    for r in runs:
        if not isinstance(r, dict) or not r.get("run_id"):
            continue
        status = r.get("status", "?")
        emoji = {"done": "✅", "failed": "❌", "running": "🔄",
                 "cancelled": "⏹️"}.get(status, "❔")
        run_id = r.get("run_id", "?")
        source = r.get("source", "?")
        operation = r.get("operation", "?")
        with st.expander(f"{emoji} {run_id} — {source} ({operation})"):
            st.json(r)


def main() -> None:
    st.set_page_config(page_title="Admin RAG", page_icon="⚙️", layout="wide")
    st.title("⚙️ Administration du pipeline RAG")

    ok = weaviate_ready()
    if not ok:
        st.warning(f"Weaviate injoignable sur {config.WEAVIATE_HOST}:{config.WEAVIATE_PORT} — "
                   "les collections affichées seront vides (les runs restent possibles).")

    counts = collection_counts()

    with st.container(border=True):
        st.subheader("Sources")
        data = [
            {
                "source": s["name"],
                "collection": s["collection"],
                "type": s["type"],
                "objets": counts.get(s["name"]) if counts else "—",
            }
            for s in config.SOURCES
        ]
        st.dataframe(data, use_container_width=True)

    with st.container(border=True):
        st.subheader("Lancer un run")
        source = st.selectbox("Source", SOURCE_CHOICES, key="run_source")
        label = st.radio("Opération", list(START_STEPS) + ["Purge collection"], key="op")

        if label != "Purge collection":
            st.session_state["confirm_purge"] = False

        running = active_running_state()
        if running:
            st.warning("Un run est déjà en cours — lancement et purge désactivés "
                       "jusqu'à son terme.")

        col1, col2 = st.columns(2)
        if col1.button("Lancer", type="primary", use_container_width=True, disabled=running):
            if label == "Purge collection":
                st.session_state["confirm_purge"] = True
            else:
                launch_ingest(source, label)
        if st.session_state.get("confirm_purge") and label == "Purge collection":
            col2.button(
                f"⚠️ Confirmer la purge de {config.get_collection(source)}",
                on_click=lambda s=source: purge_collection(s),
                use_container_width=True,
                disabled=running,
            )
        if col2.button("Actualiser", use_container_width=True):
            st.rerun()

    entry = st.session_state.get("active")
    if entry:
        path = Path(entry["path"])
        rec = read_run(path)
        proc = st.session_state.get("proc")
        with st.container(border=True):
            st.subheader(f"Run actif — {entry['source']} ({entry['label']})")
            if rec is None:
                st.info("Démarrage du runner…")
            else:
                render_run(rec)
            terminal = rec is not None and rec.get("status") in TERMINAL
            if st.button("⏹️ Arrêter (kill)", key="kill", disabled=terminal):
                kill_active(entry)
                st.rerun()

        if rec is not None and rec.get("status") not in TERMINAL:
            time.sleep(1)
            st.rerun()
        elif rec is not None:
            # Statut terminal : on nettoie l'entrée active et on rafraîchit.
            st.session_state.pop("active", None)
            st.session_state.pop("proc", None)
            st.rerun()
        elif proc is not None and proc.poll() is None:
            # Fichier pas encore écrit mais process vivant : on continue de poller.
            time.sleep(1)
            st.rerun()
        elif proc is not None:
            # Le runner est mort avant d'avoir créé le fichier : run failed explicite.
            STATUS_DIR.mkdir(parents=True, exist_ok=True)
            start_step = START_STEPS.get(entry["label"])
            create_run_file(path, run_id=entry["run_id"], source=entry["source"],
                            operation="ingest", start_step=start_step,
                            steps=[start_step] if start_step else [], status_dir=STATUS_DIR)
            mark_failed(path, "le runner s'est arrêté avant de créer le fichier de statut")
            st.session_state.pop("active", None)
            st.session_state.pop("proc", None)
            st.rerun()
        else:
            # Ni fichier ni process : entrée fantôme, on nettoie la session.
            st.session_state.pop("active", None)
            st.session_state.pop("proc", None)
            st.rerun()

    with st.container(border=True):
        st.subheader("Historique des runs")
        render_history()


if __name__ == "__main__":
    main()
