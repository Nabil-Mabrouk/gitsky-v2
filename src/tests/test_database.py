"""Contrat de `get_db` — stack SQLAlchemy async (Phase 1, incrément 2).

Prouve que `get_db` fournit une `AsyncSession` opérationnelle (aller-retour réel
insert/select). On utilise un moteur SQLite in-memory dédié (StaticPool = une
seule connexion partagée) injecté dans `SessionLocal`, ce qui rend le test
totalement indépendant de l'ordre d'import et de la config par défaut (le moteur
module-level est construit à l'import à partir de settings mis en cache).
"""

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import Integer, String, select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Mapped, mapped_column  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.core.database as database  # noqa: E402
from app.core.database import Base  # noqa: E402


class _Item(Base):
    __tablename__ = "items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)


def test_get_db_yields_working_session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Injecte notre factory in-memory dans le module : get_db l'utilise au runtime.
    database.SessionLocal = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async def scenario() -> str:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Exactement le chemin que FastAPI emprunte via Depends(get_db).
        agen = database.get_db()
        db = await agen.__anext__()
        try:
            db.add(_Item(name="gizmo"))
            await db.commit()
            result = await db.execute(select(_Item).where(_Item.name == "gizmo"))
            return result.scalar_one().name
        finally:
            await agen.aclose()

    try:
        assert asyncio.run(scenario()) == "gizmo"
    finally:
        asyncio.run(engine.dispose())
