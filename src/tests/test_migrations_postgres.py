"""Chaînes de migrations Alembic contre un vrai PostgreSQL (pas SQLite).

test_migrations.py couvre les chaînes en SQLite, où les colonnes `Enum`
sont émulées en VARCHAR + CHECK — aucun `CREATE TYPE` n'existe côté SQLite,
ce qui masque structurellement les bugs de réutilisation d'enum PostgreSQL
nommé entre chaînes Alembic distinctes. Trouvé en déploiement réel : la
chaîne tutorials retentait un `CREATE TYPE userrole` déjà créé par la
chaîne core (DuplicateObjectError) malgré `create_type=False` sur un
`sa.Enum` générique — silencieux en SQLite, invisible avant PostgreSQL.

Lourd (conteneur Docker) : ignoré si `docker` est indisponible, comme
test_docker_build_integration.py.
"""

import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from app.core.config import Settings  # noqa: E402
from scripts.migrate import run_migrations  # noqa: E402

DOCKER = shutil.which("docker")
pytestmark = pytest.mark.skipif(not DOCKER, reason="docker requis")

_CONTAINER = "gitsky-test-migrations-pg"
_PORT = 15432
# ssl=disable : le conteneur postgres:16.3-alpine jetable n'a pas de TLS
# configuré. En "prefer" (défaut asyncpg), une négociation SSL avortée a
# provoqué un ConnectionError intermittent en CI (Docker-in-Docker) plutôt
# qu'un repli propre en clair — la désactiver évite la négociation entière.
_URL = f"postgresql+asyncpg://postgres:test@localhost:{_PORT}/testdb?ssl=disable"


@pytest.fixture(scope="module")
def postgres_url():
    subprocess.run(["docker", "rm", "-f", _CONTAINER], capture_output=True)
    subprocess.run(
        [
            "docker", "run", "-d", "--name", _CONTAINER,
            "-e", "POSTGRES_PASSWORD=test", "-e", "POSTGRES_DB=testdb",
            "-p", f"{_PORT}:5432", "postgres:16.3-alpine",
        ],
        check=True, capture_output=True,
    )
    try:
        for _ in range(30):
            r = subprocess.run(
                ["docker", "exec", _CONTAINER, "pg_isready", "-U", "postgres"],
                capture_output=True,
            )
            if r.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Postgres n'a jamais répondu prêt")
        yield _URL
    finally:
        subprocess.run(["docker", "rm", "-f", _CONTAINER], capture_output=True)


def test_tutorials_chain_reuses_userrole_enum_without_duplicate_error(postgres_url):
    # Reproduit le scénario réel : core (+ autres chaînes) déjà appliqué,
    # tutorials activé ensuite — l'enum `userrole` existe déjà, la chaîne
    # tutorials doit le réutiliser, jamais tenter de le recréer.
    settings_before = Settings(gitsky_tier="t2", database_url=postgres_url)
    applied_before = run_migrations(url=postgres_url, settings=settings_before)
    assert "core" in applied_before
    assert "tutorials" not in applied_before

    settings_after = Settings(
        gitsky_tier="t2", module_tutorials=True, database_url=postgres_url
    )
    applied_after = run_migrations(url=postgres_url, settings=settings_after)
    assert "tutorials" in applied_after
