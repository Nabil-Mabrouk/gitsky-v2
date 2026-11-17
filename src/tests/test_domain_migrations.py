"""Chaîne Alembic `domain` dans un projet GÉNÉRÉ (bug réel 0-hl, 2026-11-18).

Scénario développeur complet, en sous-processus dans le projet rendu (le test
de test_migrations.py migre le template brut, sans app/domain/models.py) :
migrate -> modèle métier -> `alembic -n domain revision --autogenerate` ->
migrate -> la table métier existe, users est intact.
"""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

from helpers import projet_genere  # noqa: E402


def _run(args: list[str], cwd: Path, db_file: Path) -> str:
    env = {
        **os.environ,
        "PYTHONPATH": str(cwd),
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_file.as_posix()}",
        "ENVIRONMENT": "development",
    }
    result = subprocess.run(
        [sys.executable, *args], cwd=cwd, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def _tables(db_file: Path) -> set[str]:
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_domain_model_reaches_the_database_through_the_migrate_runner():
    models = [{"name": "Signal", "fields": {"symbol": "str", "price": "float"}}]
    with projet_genere("zero-hl", data_models=models) as dst:
        db_file = dst / "test.db"

        _run(["-m", "scripts.migrate"], dst, db_file)
        assert "users" in _tables(db_file)
        assert "signals" not in _tables(db_file)

        _run(["-m", "alembic", "-n", "domain", "revision", "--autogenerate", "-m", "init"], dst, db_file)
        revisions = list((dst / "alembic" / "domain" / "versions").glob("*.py"))
        assert len(revisions) == 1
        source = revisions[0].read_text(encoding="utf-8")
        assert "create_table('signals'" in source or 'create_table("signals"' in source
        # upgrade() ne doit jamais supprimer les tables hors chaîne domain
        # (users, modules) ; downgrade() supprime légitimement signals.
        upgrade = source.split("def upgrade()")[1].split("def downgrade()")[0]
        assert "drop_table" not in upgrade
        assert "'users'" not in source and '"users"' not in source

        out = _run(["-m", "scripts.migrate"], dst, db_file)
        assert "domain" in out
        tables = _tables(db_file)
        assert {"users", "signals", "alembic_version_domain"} <= tables
