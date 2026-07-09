"""Environnement Alembic — chaîne module `monetization` (async).

Table de version dédiée `alembic_version_monetization`. Appliquée si l'un des
deux flags monétisation est actif (shop ou subscription).
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.database import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_settings = get_settings()
_url = config.get_main_option("sqlalchemy.url") or _settings.database_url
_version_table = (
    config.get_main_option("version_table") or "alembic_version_monetization"
)


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
