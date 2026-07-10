"""Module analytics (Phase 3) — anonymisation, tracking, agrégation admin.

hash_ip (pur) + TrackingMiddleware (stocke une visite hashée, non bloquant) +
routeur admin (world/paths, protégé). Base SQLite fichier ; SessionLocal patché.
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
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.database as database  # noqa: E402
import app.core.models  # noqa: E402,F401
from app.core.auth.security import create_access_token, hash_password  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.models import User, UserRole  # noqa: E402
from app.modules.analytics import TrackingMiddleware  # noqa: E402
from app.modules.analytics import router as analytics_router  # noqa: E402
from app.modules.analytics.geoip import geolocate, hash_ip  # noqa: E402
from app.modules.analytics.models import Visit  # noqa: E402


# --- Anonymisation (pur) --------------------------------------------------

def test_hash_ip_deterministic_salted_and_opaque():
    h = hash_ip("203.0.113.7", "project-salt")
    assert h == hash_ip("203.0.113.7", "project-salt")  # déterministe
    assert h != hash_ip("203.0.113.7", "autre-sel")  # le sel change le hash
    assert "203.0.113.7" not in h  # l'IP n'apparaît jamais
    assert len(h) == 64  # SHA-256 hex


def test_geolocate_fallbacks_without_service(monkeypatch):
    monkeypatch.delenv("GEOIP_URL", raising=False)
    assert geolocate("1.2.3.4") == {"country_code": "??", "city": None}


def test_geolocate_uses_shared_service_when_configured(monkeypatch):
    import httpx

    monkeypatch.setenv("GEOIP_URL", "http://geoip")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"country_code": "FR", "city": "Paris"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert geolocate("1.2.3.4", client=client) == {
        "country_code": "FR",
        "city": "Paris",
    }


# --- Intégration middleware + routeur admin -------------------------------

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_analytics_{os.getpid()}.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}")
factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
database.SessionLocal = factory

SEED: dict[str, int] = {}


async def _seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        admin = User(email="a@x.com", hashed_password=hash_password("x"), role=UserRole.admin)
        user = User(email="u@x.com", hashed_password=hash_password("x"), role=UserRole.user)
        db.add_all([admin, user])
        db.add_all(
            [
                Visit(ip_hash="h1", country_code="FR", path="/pricing"),
                Visit(ip_hash="h2", country_code="FR", path="/pricing"),
            ]
        )
        await db.commit()
        await db.refresh(admin)
        await db.refresh(user)
        SEED.update(admin_id=admin.id, user_id=user.id)


asyncio.run(_seed())


async def _override_get_db():
    async with factory() as session:
        yield session


app = FastAPI()
app.add_middleware(TrackingMiddleware)
app.include_router(analytics_router, prefix="/api/admin/analytics")


@app.get("/")
async def root() -> dict:
    return {"ok": True}


app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)


@atexit.register
def _cleanup() -> None:
    asyncio.run(engine.dispose())
    try:
        _DB_FILE.unlink()
    except OSError:
        pass


def _auth(user_id: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


async def _all_visits() -> list[Visit]:
    async with factory() as db:
        return list((await db.execute(select(Visit))).scalars().all())


def test_tracking_stores_hashed_visit_not_blocked():
    database.SessionLocal = factory  # d'autres tests réassignent le global
    before = len(asyncio.run(_all_visits()))

    r = client.get("/")
    assert r.status_code == 200  # la réponse n'est jamais bloquée

    visits = asyncio.run(_all_visits())
    assert len(visits) == before + 1
    latest = visits[-1]
    assert latest.path == "/"
    assert latest.country_code == "??"  # géoloc stub
    # IP hashée : le host TestClient ("testclient") n'apparaît pas en clair.
    assert "testclient" not in (latest.ip_hash or "")


def test_world_aggregation_admin_only():
    # Protection.
    assert client.get("/api/admin/analytics/world").status_code == 401
    assert (
        client.get("/api/admin/analytics/world", headers=_auth(SEED["user_id"])).status_code
        == 403
    )
    # Admin : agrégation par pays.
    r = client.get("/api/admin/analytics/world", headers=_auth(SEED["admin_id"]))
    assert r.status_code == 200
    counts = {row["country_code"]: row["visits"] for row in r.json()}
    assert counts.get("FR", 0) >= 2


def test_paths_aggregation_admin():
    r = client.get("/api/admin/analytics/paths", headers=_auth(SEED["admin_id"]))
    assert r.status_code == 200
    paths = {row["path"]: row["visits"] for row in r.json()}
    assert paths.get("/pricing", 0) >= 2
