"""Token d'enregistrement fleet (durcissement).

POST /api/fleet/projects/register était public : n'importe qui pouvait créer ou
ÉCRASER (tier, domaine) les projets de la flotte. Contrat :

- token configuré  -> header X-Fleet-Token obligatoire et exact (sinon 401) ;
- token absent     -> ouvert en dev (philosophie stub), mais REFUS (503) en
  production : fail-closed, jamais un register public en prod ;
- côté générateur, `register_fleet.register` transmet le header.
"""

import asyncio
import atexit
import os
import sys
import tempfile
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generator" / "tasks"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.models  # noqa: E402,F401
import app.modules.fleet.models  # noqa: E402,F401
import register_fleet  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_fleet_token_{os.getpid()}.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}")
factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


asyncio.run(_create_tables())


async def _override_get_db():
    async with factory() as session:
        yield session


from app.modules.fleet import router as fleet_router  # noqa: E402

app = FastAPI()
app.include_router(fleet_router, prefix="/api/fleet")
app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)

PAYLOAD = {"name": "guarded", "tier": "t0"}


@atexit.register
def _cleanup() -> None:
    asyncio.run(engine.dispose())
    try:
        _DB_FILE.unlink()
    except OSError:
        pass


def _with_settings(**overrides):
    """Mutations temporaires du singleton Settings (lru_cache) avec restauration."""
    settings = get_settings()
    saved = {k: getattr(settings, k) for k in overrides}
    for k, v in overrides.items():
        setattr(settings, k, v)
    return settings, saved


def _restore(saved: dict) -> None:
    settings = get_settings()
    for k, v in saved.items():
        setattr(settings, k, v)


def test_register_with_valid_token():
    _, saved = _with_settings(fleet_register_token="s3cret-fleet")
    try:
        r = client.post(
            "/api/fleet/projects/register",
            json=PAYLOAD,
            headers={"X-Fleet-Token": "s3cret-fleet"},
        )
        assert r.status_code == 200
    finally:
        _restore(saved)


def test_register_rejects_missing_or_wrong_token():
    _, saved = _with_settings(fleet_register_token="s3cret-fleet")
    try:
        assert client.post("/api/fleet/projects/register", json=PAYLOAD).status_code == 401
        r = client.post(
            "/api/fleet/projects/register",
            json=PAYLOAD,
            headers={"X-Fleet-Token": "mauvais"},
        )
        assert r.status_code == 401
    finally:
        _restore(saved)


def test_register_fail_closed_in_production_without_token():
    _, saved = _with_settings(fleet_register_token="", environment="production")
    try:
        r = client.post("/api/fleet/projects/register", json=PAYLOAD)
        assert r.status_code == 503
    finally:
        _restore(saved)


def test_register_stays_open_in_dev_without_token():
    _, saved = _with_settings(fleet_register_token="", environment="development")
    try:
        assert client.post("/api/fleet/projects/register", json=PAYLOAD).status_code == 200
    finally:
        _restore(saved)


# --- Côté générateur : la task envoie le header -----------------------------

def test_generator_task_sends_token_header(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["token"] = request.headers.get("X-Fleet-Token")
        return httpx.Response(200, json={"name": "p", "tier": "t0"})

    fake = httpx.Client(transport=httpx.MockTransport(handler))
    register_fleet.register(
        project="p",
        tier="t0",
        domain="p.mystudio.com",
        template_version="1.0.0",
        fleet_url="http://fleet.local",
        token="s3cret-fleet",
        client=fake,
    )
    assert seen["token"] == "s3cret-fleet"
