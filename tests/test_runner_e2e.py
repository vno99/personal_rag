"""Test d'intégration du runner via subprocess réel (cf. code review K).

Couvre la chaîne complète :
  subprocess → `python app/runner.py ...` → `execute_run()` → `status_writer`
y compris le couplage `cwd` / `sys.path` (cf. PR #4) qui ne peut pas
être validé par un test unitaire sur `execute_run`.

Approche : on lance le runner avec des arguments invalides, ce qui fait
échouer argparse (exit 2) ou le code métier (exit 1). Le test vérifie
que le runner :
  1. démarre correctement (cwd + sys.path) — pas de ModuleNotFoundError
  2. retourne un code d'erreur non nul
  3. émet l'erreur sur stderr (pas silencieusement avalée)

C'est le test e2e le moins cher : pas de réseau, pas de Weaviate,
pas de chargement du tokenizer, <1 seconde.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_runner(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "app/runner.py", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_runner_subprocess_resolves_cwd():
    """Le runner, lancé en subprocess avec `cwd=REPO_ROOT`, résout
    correctement ses imports (`from get_docs import run`,
    `from status_writer import ...`).

    Si ce test échoue avec ModuleNotFoundError, c'est que l'admin
    (qui lance le runner avec `cwd=ROOT`) ne pourra plus le lancer —
    c'est le couplage cwd/sys.path de la PR #4 qui est ici validé.
    """
    # argparse catch la source invalide → exit 2 + message clair.
    result = _run_runner(
        "--source",
        "source_qui_nexiste_pas_e2e",
        "--run-id",
        "2099-12-31T23-59-59-e2e-cwd",
        "--operation",
        "ingest",
        "--start-step",
        "get_docs",
    )
    assert result.returncode != 0, f"Le runner devrait échouer sur source inconnue. stderr={result.stderr!r}"
    # Pas d'ImportError : cwd + sys.path résolus.
    assert "ModuleNotFoundError" not in result.stderr, (
        f"Le runner n'arrive pas à résoudre ses imports (cwd/sys.path). stderr={result.stderr!r}"
    )
    # L'erreur est sur stderr (pas silencieusement avalée).
    assert "invalid choice" in result.stderr or "ValueError" in result.stderr


def test_runner_subprocess_rejects_unknown_start_step():
    """argparse valide `start_step` : un step inconnu doit lever une
    erreur argparse (exit 2 + message clair) sans crasher Python.
    """
    result = _run_runner(
        "--source",
        "python",
        "--run-id",
        "2099-12-31T23-59-59-e2e-step",
        "--operation",
        "ingest",
        "--start-step",
        "step_qui_nexiste_pas",
    )
    assert result.returncode == 2, f"argparse doit rejeter un start_step invalide (exit 2). stderr={result.stderr!r}"
    assert "invalid choice" in result.stderr
    assert "step_qui_nexiste_pas" in result.stderr


def test_runner_subprocess_help_works():
    """Sanity check : `--help` doit passer, ce qui prouve que la chaîne
    `python app/runner.py --help` fonctionne de bout en bout (Python
    trouve le module, argparse parse OK).

    On évite les caractères accentués dans l'assertion : stdout est
    décodé en cp1252 sur Windows (cf. sys.stdout.encoding), et pytest
    capture avec l'encoding du terminal parent. Un 'è' devient '�' côté
    assert, et le test échoue sur des machines où l'encoding diffère.
    """
    result = _run_runner("--help")
    assert result.returncode == 0
    # Mots-clés ASCII (toujours présents) : on valide la description
    # sans dépendre de l'encoding.
    assert "run d" in result.stdout
    assert "--source" in result.stdout
    assert "--start-step" in result.stdout
