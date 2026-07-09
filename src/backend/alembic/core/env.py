"""Environnement Alembic — chaîne `core` (async).

Pattern async : `create_async_engine` + `connection.run_sync(run_migrations)`.
L'URL vient des settings (DATABASE_URL) sauf override `sqlalchemy.url` (tests).
La `version_table` est propre à chaque chaîne (ici `alembic_version_core`) pour
cohabiter avec les chaînes des modules dans une seule base par projet.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.database import Base
import app.core.models  # noqa: F401  (enregistre User sur Base.metadata)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_settings = get_settings()
_url = config.get_main_option("sqlalchemy.url") or _settings.database_url
_version_table = config.get_main_option("version_table") or "alembic_version_core"


def _configure(connection=None, url=None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        version_table=_version_table,
        compare_type=True,
    )


def run_migrations_offline() -> None:
    _configure(url=_url)
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_url)
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
