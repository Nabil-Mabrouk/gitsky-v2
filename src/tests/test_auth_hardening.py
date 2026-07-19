"""Durcissement auth : logout côté serveur + politique de mot de passe.

1. Logout — `AuthContext.logout()` ne vidait que le localStorage : le cookie
   refresh HttpOnly restait valable 7 jours sur la machine. Contrat : POST
   /api/auth/logout expire le cookie, et un refresh ultérieur échoue.

2. Mot de passe — register acceptait "" ou "a". Contrat : min 8 caractères au
   register (422 sinon), mais le LOGIN reste non contraint pour ne jamais
   verrouiller un compte créé avant la règle.
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
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.models  # noqa: E402,F401
from app.core.auth import router as auth_router  # noqa: E402
from app.core.auth.security import hash_password  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.models import User  # noqa: E402

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_auth_hard_{os.getpid()}.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}")
factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        # Compte « legacy » créé avant la politique de mot de passe.
        db.add(User(email="legacy@x.com", hashed_password=hash_password("abc")))
        await db.commit()


asyncio.run(_seed())


async def _override_get_db():
    async with factory() as session:
        yield session


app = FastAPI()
app.include_router(auth_router, prefix="/api/auth")
app.dependency_overrides[get_db] = _override_get_db


@atexit.register
def _cleanup() -> None:
    asyncio.run(engine.dispose())
    try:
        _DB_FILE.unlink()
    except OSError:
        pass


# --- Logout ---------------------------------------------------------------

def test_logout_expires_refresh_cookie_and_kills_refresh():
    client = TestClient(app)
    creds = {"email": "carol@x.com", "password": "long-enough-pass"}
    assert client.post("/api/auth/register", json=creds).status_code == 201
    assert client.post("/api/auth/login", json=creds).status_code == 200

    # Le cookie posé au login permet un refresh.
    assert client.post("/api/auth/refresh").status_code == 200

    r = client.post("/api/auth/logout")
    assert r.status_code in (200, 204)

    # Cookie expiré côté client : le refresh ne passe plus.
    assert client.post("/api/auth/refresh").status_code == 401


def test_logout_without_session_is_harmless():
    client = TestClient(app)
    assert client.post("/api/auth/logout").status_code in (200, 204)


# --- Politique de mot de passe --------------------------------------------

def test_register_rejects_short_password():
    client = TestClient(app)
    r = client.post(
        "/api/auth/register", json={"email": "dave@x.com", "password": "court"}
    )
    assert r.status_code == 422


def test_login_still_accepts_legacy_short_password():
    client = TestClient(app)
    r = client.post(
        "/api/auth/login", json={"email": "legacy@x.com", "password": "abc"}
    )
    assert r.status_code == 200
