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

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
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
from app.core.auth.security import create_reset_token  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.models import User  # noqa: E402

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


# --- Chap 7bis : mot de passe imposé + réinitialisation ------------------


async def _get_user_by_email(email: str) -> User:
    async with TestingSession() as db:
        from sqlalchemy import select as _select

        return (
            await db.execute(_select(User).where(User.email == email))
        ).scalar_one()


async def _set_must_change_password(email: str) -> None:
    async with TestingSession() as db:
        from sqlalchemy import select as _select

        user = (
            await db.execute(_select(User).where(User.email == email))
        ).scalar_one()
        user.must_change_password = True
        await db.commit()


def test_login_reports_must_change_password_flag():
    creds = {"email": "bob@example.com", "password": "s3cret-pass"}
    client.post("/api/auth/register", json=creds)
    # /register ne force jamais le changement — seul un compte créé par un
    # tiers (create_admin.sh) l'active ; simulé ici directement en base,
    # aucun endpoint public ne peut le poser.
    asyncio.run(_set_must_change_password(creds["email"]))

    login = client.post("/api/auth/login", json=creds)
    assert login.status_code == 200, login.text
    assert login.json()["must_change_password"] is True


def test_forgot_password_always_returns_202_even_for_unknown_email():
    r = client.post(
        "/api/auth/forgot-password", json={"email": "personne@example.com"}
    )
    assert r.status_code == 202


def test_forgot_password_sets_reset_token_for_known_email():
    creds = {"email": "carol@example.com", "password": "s3cret-pass"}
    client.post("/api/auth/register", json=creds)

    r = client.post("/api/auth/forgot-password", json={"email": creds["email"]})
    assert r.status_code == 202

    user = asyncio.run(_get_user_by_email(creds["email"]))
    assert user.reset_token is not None


def test_reset_password_with_valid_token_logs_in_and_clears_flags():
    creds = {"email": "dave@example.com", "password": "s3cret-pass"}
    client.post("/api/auth/register", json=creds)
    asyncio.run(_set_must_change_password(creds["email"]))
    user = asyncio.run(_get_user_by_email(creds["email"]))
    old_token_version = user.token_version

    token = create_reset_token(user.id)

    async def _store_token() -> None:
        async with TestingSession() as db:
            u = await db.get(User, user.id)
            assert u is not None
            u.reset_token = token
            await db.commit()

    asyncio.run(_store_token())

    r = client.post(
        "/api/auth/reset-password",
        json={"token": token, "password": "nouveau-mdp-1"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["access_token"]

    refreshed = asyncio.run(_get_user_by_email(creds["email"]))
    assert refreshed.reset_token is None
    assert refreshed.must_change_password is False
    assert refreshed.token_version == old_token_version + 1

    # L'ancien mot de passe ne fonctionne plus, le nouveau si.
    assert client.post("/api/auth/login", json=creds).status_code == 401
    assert (
        client.post(
            "/api/auth/login",
            json={"email": creds["email"], "password": "nouveau-mdp-1"},
        ).status_code
        == 200
    )


def test_reset_password_rejects_reused_token():
    creds = {"email": "erin@example.com", "password": "s3cret-pass"}
    client.post("/api/auth/register", json=creds)
    user = asyncio.run(_get_user_by_email(creds["email"]))
    token = create_reset_token(user.id)

    async def _store_token() -> None:
        async with TestingSession() as db:
            u = await db.get(User, user.id)
            assert u is not None
            u.reset_token = token
            await db.commit()

    asyncio.run(_store_token())

    first = client.post(
        "/api/auth/reset-password", json={"token": token, "password": "premier-mdp1"}
    )
    assert first.status_code == 200, first.text

    # Le jeton a été consommé (reset_token remis à NULL) : le rejouer échoue.
    second = client.post(
        "/api/auth/reset-password", json={"token": token, "password": "second-mdp12"}
    )
    assert second.status_code == 401


def test_reset_password_rejects_wrong_token_type():
    r = client.post(
        "/api/auth/reset-password",
        json={"token": "not.a.jwt", "password": "peu-importe1"},
    )
    assert r.status_code == 401


def test_change_password_requires_current_password():
    creds = {"email": "frank@example.com", "password": "s3cret-pass"}
    client.post("/api/auth/register", json=creds)
    access = client.post("/api/auth/login", json=creds).json()["access_token"]

    r = client.patch(
        "/api/auth/change-password",
        json={"current_password": "faux-mdp", "new_password": "nouveau-mdp1"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 401


def test_change_password_success_clears_flag_and_revokes_old_session():
    creds = {"email": "grace@example.com", "password": "s3cret-pass"}
    client.post("/api/auth/register", json=creds)
    asyncio.run(_set_must_change_password(creds["email"]))
    login = client.post("/api/auth/login", json=creds)
    access = login.json()["access_token"]
    # Capturé explicitement : /change-password pose son propre cookie frais
    # (même motif que /reset-password), qui écraserait celui-ci dans le
    # cookie-jar partagé du TestClient avant qu'on ait pu le rejouer.
    stale_cookie = login.cookies["refresh_token"]

    r = client.patch(
        "/api/auth/change-password",
        json={"current_password": creds["password"], "new_password": "nouveau-mdp1"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200, r.text

    refreshed = asyncio.run(_get_user_by_email(creds["email"]))
    assert refreshed.must_change_password is False

    # Le refresh token émis AVANT le changement est révoqué (token_version
    # incrémenté) — rejoué explicitement, pas via le cookie-jar du client
    # (qui a déjà adopté le nouveau cookie posé par la réponse ci-dessus).
    stale_refresh = client.post(
        "/api/auth/refresh", headers={"Cookie": f"refresh_token={stale_cookie}"}
    )
    assert stale_refresh.status_code == 401

    # Le cookie tout juste posé par /change-password, lui, fonctionne bien.
    fresh_refresh = client.post("/api/auth/refresh")
    assert fresh_refresh.status_code == 200, fresh_refresh.text
