"""Validation Docker RÉELLE de bout en bout (Phase 6, incr 8 — Chap 21/23).

Contrairement aux tests structurels (test_docker_prod*.py), on BUILDE vraiment
l'image et on la LANCE. Coûteux (minutes) et dépendant du réseau : désactivé par
défaut, activé par GITSKY_DOCKER_IT=1.

    GITSKY_DOCKER_IT=1 python -m pytest src/tests/test_docker_build_integration.py

Auto-suffisant : le conteneur est lancé avec un DATABASE_URL SQLite dans /data,
pour ne pas dépendre d'un Postgres externe dans ce test. Valide les corrections
trouvées AU build : non-root, /app en lecture seule mais /data inscriptible,
HEALTHCHECK Python -> /health à 200.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

if os.environ.get("GITSKY_DOCKER_IT") != "1":
    pytest.skip("intégration Docker (poser GITSKY_DOCKER_IT=1)", allow_module_level=True)

if shutil.which("docker") is None:
    pytest.skip("docker absent", allow_module_level=True)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import projet_genere  # noqa: E402

IMAGE = "gitsky-be-it"
CONTAINER = "gitsky-be-it-run"


def _docker(*args, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, **kw)


@pytest.fixture(scope="module")
def backend_image():
    with projet_genere("it-proj") as dst:
        build = _docker("build", "-f", "Dockerfile", "-t", IMAGE, ".", cwd=str(dst))
        assert build.returncode == 0, build.stderr[-2000:]
        yield IMAGE
    _docker("rmi", "-f", IMAGE)


def test_backend_runs_non_root_health_ok(backend_image):
    _docker("rm", "-f", CONTAINER)
    run = _docker(
        "run", "-d", "--name", CONTAINER,
        "-e", "DATABASE_URL=sqlite+aiosqlite:////data/gitsky.db",
        backend_image,
    )
    assert run.returncode == 0, run.stderr
    try:
        # Laisser Gunicorn démarrer.
        health = None
        for _ in range(30):
            probe = _docker(
                "exec", CONTAINER, "python", "-c",
                "import urllib.request,json;"
                "r=urllib.request.urlopen('http://localhost:8000/health');"
                "print(r.status);print(json.dumps(json.load(r)))",
            )
            if probe.returncode == 0:
                lines = probe.stdout.strip().splitlines()
                health = (int(lines[0]), json.loads(lines[1]))
                break
            time.sleep(1)

        assert health is not None, "le backend n'a jamais répondu sur /health"
        status, body = health
        assert status == 200
        assert body["database"] == "ok"  # SELECT 1 réel (incr 4)

        # Non-root (Chap 21).
        who = _docker("exec", CONTAINER, "whoami")
        assert who.stdout.strip() == "appuser"

        # Code en lecture seule : appuser ne peut pas écrire dans /app.
        w = _docker("exec", CONTAINER, "sh", "-c", "touch /app/x 2>&1 || echo DENIED")
        assert "DENIED" in w.stdout

        # /data inscriptible (là où vit le SQLite).
        d = _docker("exec", CONTAINER, "sh", "-c", "touch /data/x && echo OK")
        assert "OK" in d.stdout
    finally:
        _docker("rm", "-f", CONTAINER)
