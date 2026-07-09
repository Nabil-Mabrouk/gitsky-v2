"""Routeur auth de bout en bout (Phase 1, incrément 4b).

Flux complet register -> login -> me -> refresh via `TestClient`, avec une base
SQLite dédiée (fichier temporaire) injectée par override de `get_db`. On utilise
un fichier plutôt qu'un in-memory pour éviter tout problème de connexion
partagée entre boucles asyncio (création des tables vs requêtes du TestClient).
"""

import asyncio
import atexit
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.models  # noqa: E402,F401  (enregistre User sur Base.metadata)
from app.core.auth import router as auth_router  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_auth_test_{os.getpid()}.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}")
TestingSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


asyncio.run(_create_tables())


async def _override_get_db():
    async with TestingSession() as session:
        yield session


app = FastAPI()
app.include_router(auth_router, prefix="/api/auth")
app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)

CREDS = {"email": "alice@example.com", "password": "s3cret-pass"}


@atexit.register
def _cleanup() -> None:
    asyncio.run(engine.dispose())
    if _DB_FILE.exists():
        _DB_FILE.unlink()


def test_register_creates_user_then_conflicts():
    r = client.post("/api/auth/register", json=CREDS)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == CREDS["email"]
    assert body["role"] == "user"
    assert body["is_active"] is True
    assert "hashed_password" not in body  # le hash ne fuite jamais

    # Un second register sur le même email est refusé.
    assert client.post("/api/auth/register", json=CREDS).status_code == 409


def test_login_rejects_wrong_password():
    assert (
        client.post(
            "/api/auth/login",
            json={"email": CREDS["email"], "password": "mauvais"},
        ).status_code
        == 401
    )


def test_login_me_and_refresh_flow():
    login = client.post("/api/auth/login", json=CREDS)
    assert login.status_code == 200, login.text
    access = login.json()["access_token"]
    assert access
    # Le refresh token part en cookie (HttpOnly côté navigateur).
    assert "refresh_token" in login.cookies

    # /me protégé : accessible avec le Bearer access token.
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200
    assert me.json()["email"] == CREDS["email"]

    # /me sans jeton -> 401.
    assert client.get("/api/auth/me").status_code == 401

    # /refresh via le cookie persisté par le client -> nouvel access token.
    refreshed = client.post("/api/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["access_token"]


def test_me_rejects_garbage_token():
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401
