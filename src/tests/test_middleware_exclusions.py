"""Exclusions des middlewares tracking/sécurité (durcissement perf/bruit).

Chaque requête coûtait jusqu'à deux sessions/commits DB (Visit + SecurityEvent),
y compris `/health` pollé toutes les 60 s par le fleet poller : ~43 000 lignes
de bruit par mois et par projet, qui noyaient les vraies visites et les vraies
détections. Contrat : les endpoints d'infrastructure (/health, /robots.txt,
/sitemap.xml) ne produisent NI visite NI événement de sécurité ; les routes
applicatives continuent d'en produire.
"""

import asyncio
import atexit
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.database as database  # noqa: E402
import app.core.models  # noqa: E402,F401
import app.modules.analytics.models  # noqa: E402,F401
import app.modules.security.models  # noqa: E402,F401
from app.core.database import Base  # noqa: E402
from app.modules.analytics import TrackingMiddleware  # noqa: E402
from app.modules.analytics.models import Visit  # noqa: E402
from app.modules.security import SecurityMiddleware  # noqa: E402
from app.modules.security.models import SecurityEvent  # noqa: E402

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_mw_excl_{os.getpid()}.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}")
factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


asyncio.run(_create_tables())

app = FastAPI()
app.add_middleware(TrackingMiddleware)
app.add_middleware(SecurityMiddleware)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/produits")
async def produits() -> dict:
    return {"ok": True}


client = TestClient(app)


@atexit.register
def _cleanup() -> None:
    asyncio.run(engine.dispose())
    try:
        _DB_FILE.unlink()
    except OSError:
        pass


async def _count(model) -> int:
    async with factory() as db:
        return (await db.execute(select(func.count()).select_from(model))).scalar_one()


def _counts() -> tuple[int, int]:
    return (
        asyncio.run(_count(Visit)),
        asyncio.run(_count(SecurityEvent)),
    )


def test_health_produces_no_visit_and_no_security_event(monkeypatch):
    monkeypatch.setattr(database, "SessionLocal", factory)
    visits_before, events_before = _counts()

    # Même avec une charge d'attaque dans la query : /health reste hors radar
    # (le blocage réseau est le rôle de Traefik/fail2ban, pas du tracking).
    assert client.get("/health").status_code == 200
    assert client.get("/health?q=%27%20OR%201%3D1").status_code == 200

    assert _counts() == (visits_before, events_before)


def test_application_routes_are_still_tracked(monkeypatch):
    monkeypatch.setattr(database, "SessionLocal", factory)
    visits_before, events_before = _counts()

    assert client.get("/produits").status_code == 200
    assert client.get("/produits?q=%27%20OR%201%3D1").status_code == 200

    visits_after, events_after = _counts()
    assert visits_after == visits_before + 2  # le tracking fonctionne toujours
    assert events_after == events_before + 1  # l'injection est toujours détectée
