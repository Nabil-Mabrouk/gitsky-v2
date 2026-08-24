"""Onglets Utilisateurs + Waitlist (Phase 3 Round 2, chap 9) — routeur admin
`/users*` et l'endpoint public `/api/auth/accept-invite`.

Base SQLite fichier ; SessionLocal patché pour les deux routeurs (même motif
que test_security_runtime.py). mailer.send_email est monkeypatché : pas de
vrai SMTP en test, on vérifie juste qu'il est appelé avec le bon destinataire
et un lien contenant le jeton.
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

import app.core.database as database  # noqa: E402
import app.core.models  # noqa: E402,F401  (enregistre User)
from app.core import mailer  # noqa: E402
from app.core.auth import router as auth_router  # noqa: E402  (APIRouter, cf. __init__)
from app.core.auth.security import create_access_token, hash_password  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.models import User, UserRole  # noqa: E402
from app.modules.admin import router as admin_router  # noqa: E402  (APIRouter, cf. __init__)

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_admin_users_{os.getpid()}.db"
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
        waiting = User(
            email="w@x.com", hashed_password=hash_password("x"), role=UserRole.waitlist
        )
        db.add_all([admin, user, waiting])
        await db.commit()
        await db.refresh(admin)
        await db.refresh(user)
        await db.refresh(waiting)
        SEED.update(admin_id=admin.id, user_id=user.id, waitlist_id=waiting.id)


asyncio.run(_seed())


async def _override_get_db():
    async with factory() as session:
        yield session


app = FastAPI()
app.include_router(admin_router, prefix="/api/admin")
app.include_router(auth_router, prefix="/api/auth")
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


def setup_function() -> None:
    database.SessionLocal = factory


def test_list_users_requires_admin():
    assert client.get("/api/admin/users").status_code == 401
    assert (
        client.get("/api/admin/users", headers=_auth(SEED["user_id"])).status_code == 403
    )
    r = client.get("/api/admin/users", headers=_auth(SEED["admin_id"]))
    assert r.status_code == 200
    emails = {u["email"] for u in r.json()}
    assert {"a@x.com", "u@x.com", "w@x.com"} <= emails


def test_list_users_filters_by_role():
    r = client.get(
        "/api/admin/users", params={"role": "waitlist"}, headers=_auth(SEED["admin_id"])
    )
    assert r.status_code == 200
    assert [u["email"] for u in r.json()] == ["w@x.com"]


def test_patch_user_rejects_non_admin():
    # Vérifié avant toute désactivation : réutiliser le jeton de user_id après
    # l'avoir lui-même désactivé donnerait 401 (compte inactif) et non 403.
    r = client.patch(
        f"/api/admin/users/{SEED['user_id']}",
        json={"is_active": True},
        headers=_auth(SEED["user_id"]),
    )
    assert r.status_code == 403


def test_patch_user_updates_role_and_status():
    r = client.patch(
        f"/api/admin/users/{SEED['user_id']}",
        json={"is_active": False},
        headers=_auth(SEED["admin_id"]),
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    # Remet dans l'état attendu par les tests suivants.
    client.patch(
        f"/api/admin/users/{SEED['user_id']}",
        json={"is_active": True},
        headers=_auth(SEED["admin_id"]),
    )


def test_invite_rejects_non_waitlist_user():
    r = client.post(
        f"/api/admin/users/{SEED['user_id']}/invite", headers=_auth(SEED["admin_id"])
    )
    assert r.status_code == 400


def test_invite_sends_email_and_stores_token_then_accept_invite_logs_in(monkeypatch):
    sent: dict = {}

    def fake_send_email(to: str, subject: str, body: str) -> None:
        sent["to"] = to
        sent["body"] = body

    monkeypatch.setattr(mailer, "send_email", fake_send_email)

    r = client.post(
        f"/api/admin/users/{SEED['waitlist_id']}/invite", headers=_auth(SEED["admin_id"])
    )
    assert r.status_code == 204
    assert sent["to"] == "w@x.com"
    assert "/invite/" in sent["body"]
    token = sent["body"].split("/invite/")[1].split("\n")[0]

    accept = client.post(
        "/api/auth/accept-invite", json={"token": token, "password": "longenough1"}
    )
    assert accept.status_code == 200
    assert "access_token" in accept.json()

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {accept.json()['access_token']}"})
    assert me.status_code == 200
    assert me.json()["role"] == "user"

    # Rejoué : le jeton a été consommé (invite_token remis à None).
    replay = client.post(
        "/api/auth/accept-invite", json={"token": token, "password": "longenough1"}
    )
    assert replay.status_code == 401


def test_resend_invalidates_previous_invite_token(monkeypatch):
    sent_tokens: list[str] = []

    def fake_send_email(to: str, subject: str, body: str) -> None:
        sent_tokens.append(body.split("/invite/")[1].split("\n")[0])

    monkeypatch.setattr(mailer, "send_email", fake_send_email)

    # Nouveau compte waitlist dédié à ce test (le précédent a déjà été accepté).
    async def _make_waitlist_user() -> int:
        async with factory() as db:
            u = User(
                email="w2@x.com", hashed_password=hash_password("x"), role=UserRole.waitlist
            )
            db.add(u)
            await db.commit()
            await db.refresh(u)
            return u.id

    user_id = asyncio.run(_make_waitlist_user())

    client.post(f"/api/admin/users/{user_id}/invite", headers=_auth(SEED["admin_id"]))
    client.post(f"/api/admin/users/{user_id}/invite", headers=_auth(SEED["admin_id"]))
    assert len(sent_tokens) == 2

    old_token, new_token = sent_tokens

    stale = client.post(
        "/api/auth/accept-invite", json={"token": old_token, "password": "longenough1"}
    )
    assert stale.status_code == 401

    fresh = client.post(
        "/api/auth/accept-invite", json={"token": new_token, "password": "longenough1"}
    )
    assert fresh.status_code == 200
