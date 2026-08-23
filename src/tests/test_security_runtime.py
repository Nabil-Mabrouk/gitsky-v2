"""SecurityMiddleware + routeur admin de bout en bout (Phase 3, sécurité — runtime).

Prouve la philosophie « journaliser, jamais bloquer » : une requête d'injection
reçoit une réponse normale (200) mais est enregistrée, et n'est visible que par
un admin. Base SQLite fichier ; SessionLocal patché pour le middleware.
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
import app.modules.security.models  # noqa: E402,F401  (enregistre SecurityEvent)
from app.core.auth.security import create_access_token, hash_password  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.models import User, UserRole  # noqa: E402
from app.modules.security import SecurityMiddleware  # noqa: E402
from app.modules.security import router as security_router  # noqa: E402

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_security_{os.getpid()}.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}")
factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
# Le middleware écrit via SessionLocal (module-level) : on le pointe sur le test.
database.SessionLocal = factory

SEED: dict[str, int] = {}


async def _seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        admin = User(email="a@x.com", hashed_password=hash_password("x"), role=UserRole.admin)
        user = User(email="u@x.com", hashed_password=hash_password("x"), role=UserRole.user)
        db.add_all([admin, user])
        await db.commit()
        await db.refresh(admin)
        await db.refresh(user)
        SEED.update(admin_id=admin.id, user_id=user.id)


asyncio.run(_seed())


async def _override_get_db():
    async with factory() as session:
        yield session


app = FastAPI()
app.add_middleware(SecurityMiddleware)
app.include_router(security_router, prefix="/api/admin/security")


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


def test_malicious_request_logged_but_not_blocked():
    # D'autres tests réassignent le global database.SessionLocal ; on le
    # repositionne ici pour que le middleware écrive bien dans la base du test.
    database.SessionLocal = factory

    # Injection SQL en query : la réponse doit rester normale (jamais bloquée).
    r = client.get("/", params={"q": "' OR 1=1--"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    # L'événement est visible via l'API admin.
    events = client.get(
        "/api/admin/security/events", headers=_auth(SEED["admin_id"])
    )
    assert events.status_code == 200
    assert any(e["event_type"] == "injection_attempt" for e in events.json())


def test_ip_address_uses_last_x_forwarded_for_entry_not_first():
    # Bug réel trouvé en prod (premier vrai déploiement de l'onglet
    # Sécurité) : ip_address venait de request.client.host, l'IP de Traefik
    # lui-même (le backend n'est jamais joignable directement, internal-net).
    # Traefik AJOUTE son IP à LA FIN de X-Forwarded-For — c'est ce dernier
    # maillon qui est fiable, jamais le premier (sinon un client spoofe
    # trivialement son IP journalisée en l'envoyant lui-même).
    database.SessionLocal = factory

    r = client.get(
        "/",
        params={"q": "' OR 1=1--"},
        headers={"X-Forwarded-For": "1.2.3.4, 9.9.9.9"},
    )
    assert r.status_code == 200

    events = client.get(
        "/api/admin/security/events", headers=_auth(SEED["admin_id"])
    ).json()
    assert any(e["ip_address"] == "9.9.9.9" for e in events), events
    assert not any(e["ip_address"] == "1.2.3.4" for e in events), events


def test_admin_endpoints_require_admin_role():
    # Sans jeton -> 401.
    assert client.get("/api/admin/security/summary").status_code == 401
    # Utilisateur non-admin -> 403.
    assert (
        client.get(
            "/api/admin/security/summary", headers=_auth(SEED["user_id"])
        ).status_code
        == 403
    )
    # Admin -> 200 avec la structure attendue.
    r = client.get("/api/admin/security/summary", headers=_auth(SEED["admin_id"]))
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["total"], int)
    assert isinstance(body["by_severity"], dict)
