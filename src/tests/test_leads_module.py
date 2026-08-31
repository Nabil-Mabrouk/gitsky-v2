"""Module leads de bout en bout (round leads).

`GET /api/leads` (liste, admin-only, client.fetch_leads mocké — pas d'appel
réseau réel) et `POST /api/leads/convert` (crée/invite un compte waitlist à
partir d'un email seul, réutilise create_invite_token + mailer.send_email).
Base SQLite dédiée (fichier temporaire) injectée par override de get_db —
même patron que `test_worker_module.py`/`test_tutorials_router.py`.
"""

import asyncio
import atexit
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

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

import app.core.models  # noqa: E402,F401  (enregistre User)
from app.core.auth.security import create_access_token, hash_password  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.models import User, UserRole  # noqa: E402
from app.modules.leads import router as leads_router  # noqa: E402

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_leads_{os.getpid()}.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}")
TestingSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

SEED: dict[str, int] = {}


async def _seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestingSession() as db:
        admin = User(
            email="admin@x.com", hashed_password=hash_password("x"), role=UserRole.admin
        )
        user = User(email="u@x.com", hashed_password=hash_password("x"), role=UserRole.user)
        waitlisted = User(
            email="already-waitlisted@x.com",
            hashed_password=hash_password("x"),
            role=UserRole.waitlist,
        )
        db.add_all([admin, user, waitlisted])
        await db.commit()
        await db.refresh(admin)
        await db.refresh(user)
        await db.refresh(waitlisted)
        SEED.update(admin_id=admin.id, user_id=user.id, waitlisted_id=waitlisted.id)


asyncio.run(_seed())


async def _override_get_db():
    async with TestingSession() as session:
        yield session


app = FastAPI()
app.include_router(leads_router, prefix="/api/leads")
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


def test_list_requires_auth():
    assert client.get("/api/leads").status_code == 401


def test_list_forbidden_for_plain_user():
    r = client.get("/api/leads", headers=_auth(SEED["user_id"]))
    assert r.status_code == 403


def test_list_returns_the_client_fetch_result_for_admin():
    fake_leads = [
        {
            "id": 1,
            "project": "pain-scraper",
            "email": "lead@x.com",
            "source": "landing",
            "utm_campaign": None,
            "created_at": "2026-01-01T00:00:00Z",
            "verified": False,
        }
    ]
    with patch(
        "app.modules.leads.router.client.fetch_leads", new=AsyncMock(return_value=fake_leads)
    ):
        r = client.get("/api/leads", headers=_auth(SEED["admin_id"]))
    assert r.status_code == 200
    assert r.json()[0]["email"] == "lead@x.com"


def test_convert_creates_waitlist_user_and_sends_invite_for_a_new_email():
    with patch("app.modules.leads.router.mailer.send_email") as send_email:
        r = client.post(
            "/api/leads/convert",
            json={"email": "brand-new-lead@x.com"},
            headers=_auth(SEED["admin_id"]),
        )
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "brand-new-lead@x.com"
    assert body["invited"] is True
    send_email.assert_called_once()
    assert send_email.call_args.kwargs["to"] == "brand-new-lead@x.com"

    async def _check() -> User:
        async with TestingSession() as db:
            return (
                await db.execute(select(User).where(User.email == "brand-new-lead@x.com"))
            ).scalar_one()

    user = asyncio.run(_check())
    assert user.role == UserRole.waitlist
    assert user.invite_token is not None
    # Mot de passe placeholder inutilisable, jamais le mot de passe réel d'un
    # compte accepté — seule la porte d'entrée reste accept-invite.
    assert user.hashed_password != hash_password("brand-new-lead@x.com")


def test_convert_returns_409_for_an_existing_non_waitlist_account():
    with patch("app.modules.leads.router.mailer.send_email"):
        r = client.post(
            "/api/leads/convert",
            json={"email": "u@x.com"},  # déjà un compte "user" (SEED)
            headers=_auth(SEED["admin_id"]),
        )
    assert r.status_code == 409


def test_convert_reinvites_an_existing_waitlist_account_without_duplicating():
    with patch("app.modules.leads.router.mailer.send_email") as send_email:
        r = client.post(
            "/api/leads/convert",
            json={"email": "already-waitlisted@x.com"},
            headers=_auth(SEED["admin_id"]),
        )
    assert r.status_code == 201
    assert r.json()["user_id"] == SEED["waitlisted_id"]
    send_email.assert_called_once()

    async def _count() -> int:
        async with TestingSession() as db:
            rows = (
                await db.execute(
                    select(User).where(User.email == "already-waitlisted@x.com")
                )
            ).scalars().all()
            return len(rows)

    assert asyncio.run(_count()) == 1
