"""Chaîne de migrations Alembic `core` (Phase 1, incrément 5).

Applique la chaîne core sur une base SQLite jetable via l'API Python d'Alembic
(mêmes révisions que la CLI de production) et vérifie :
- la table `users` et la table de version dédiée `alembic_version_core` ;
- les colonnes attendues ;
- l'idempotence (`upgrade head` deux fois) ;
- le `downgrade` (retrait propre de `users`).

L'URL est injectée via `sqlalchemy.url` (override), donc indépendante des
settings et de leur cache. Sous Windows, un fichier SQLite reste verrouillé tant
qu'un moteur n'est pas disposé : chaque moteur d'inspection est fermé
explicitement et la suppression finale est best-effort.
"""

import os
import sys
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from app.core.config import Settings  # noqa: E402
from scripts.migrate import run_migrations  # noqa: E402


def _make_config(db_file: Path) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic" / "core"))
    cfg.set_main_option("version_table", "alembic_version_core")
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_file.as_posix()}")
    return cfg


def _table_names(db_file: Path) -> set[str]:
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _user_columns(db_file: Path) -> set[str]:
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")
    try:
        return {c["name"] for c in inspect(engine).get_columns("users")}
    finally:
        engine.dispose()


def test_core_chain_upgrade_and_downgrade():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_file = Path(path)
    try:
        cfg = _make_config(db_file)

        command.upgrade(cfg, "head")
        command.upgrade(cfg, "head")  # idempotent : ne doit pas échouer

        tables = _table_names(db_file)
        assert "users" in tables
        # Table de version dédiée à la chaîne core (jamais `alembic_version`).
        assert "alembic_version_core" in tables
        assert "alembic_version" not in tables

        assert {
            "id",
            "email",
            "hashed_password",
            "role",
            "is_active",
            "created_at",
        } <= _user_columns(db_file)

        # Downgrade complet : la table users disparaît.
        command.downgrade(cfg, "base")
        assert "users" not in _table_names(db_file)
    finally:
        try:
            db_file.unlink()
        except OSError:
            pass  # nettoyage best-effort (verrou de fichier Windows)


def _async_url(db_file: Path) -> str:
    return f"sqlite+aiosqlite:///{db_file.as_posix()}"


def test_module_chain_skipped_when_flag_disabled():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_file = Path(path)
    try:
        # Profil T0 : analytics désactivé.
        settings = Settings(gitsky_tier="t0")
        applied = run_migrations(url=_async_url(db_file), settings=settings)

        assert applied == ["core"]
        tables = _table_names(db_file)
        assert "users" in tables
        assert "alembic_version_core" in tables
        # La chaîne analytics n'a pas tourné : ni sa table, ni sa version.
        assert "visits" not in tables
        assert "alembic_version_analytics" not in tables
    finally:
        try:
            db_file.unlink()
        except OSError:
            pass


def test_module_chain_applied_when_flag_enabled():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_file = Path(path)
    try:
        # analytics activé explicitement (indépendant du tier).
        settings = Settings(gitsky_tier="t0", module_analytics=True)
        applied = run_migrations(url=_async_url(db_file), settings=settings)

        assert applied == ["core", "analytics"]
        tables = _table_names(db_file)
        # Les deux chaînes coexistent avec leurs tables de version distinctes.
        assert {"users", "visits"} <= tables
        assert {"alembic_version_core", "alembic_version_analytics"} <= tables
    finally:
        try:
            db_file.unlink()
        except OSError:
            pass


def test_tutorials_chain_applied_when_enabled():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_file = Path(path)
    try:
        settings = Settings(gitsky_tier="t0", module_tutorials=True)
        applied = run_migrations(url=_async_url(db_file), settings=settings)

        assert applied == ["core", "tutorials"]
        tables = _table_names(db_file)
        assert {"tutorials", "lessons"} <= tables
        assert "alembic_version_tutorials" in tables
        # analytics non activé -> sa chaîne ne tourne pas.
        assert "visits" not in tables
    finally:
        try:
            db_file.unlink()
        except OSError:
            pass
