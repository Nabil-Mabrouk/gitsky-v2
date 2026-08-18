"""Découverte des modules actifs pour la sidebar admin (Chap 9).

GET /api/admin/modules — réservé à l'admin (même garde que le reste du
shell : la sécurité vit côté serveur, le frontend ne fait que suivre).
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
from app.core.auth.security import create_access_token, hash_password  # noqa: E402
from app.core.config import MODULE_FLAGS, Settings  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.models import User, UserRole  # noqa: E402
from app.modules.admin import router as admin_router  # noqa: E402

# Cf. test_fleet_health_monitor.py : `app.modules.admin.__init__` rebinde son
# propre attribut `router` sur l'APIRouter — sys.modules est le seul moyen
# fiable d'atteindre le sous-module pour patcher son `get_settings`.
admin_router_module = sys.modules["app.modules.admin.router"]

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_admin_{os.getpid()}.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}")
factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
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
app.include_router(admin_router, prefix="/api/admin")
app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)


@atexit.register
def _cleanup() -> None:
    asyncio.run(engine.dispose())
    try:
        _DB_FILE.unlink()
    except OSError:
        pass


def _auth(uid: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token(uid)}"}


def test_modules_requires_admin():
    assert client.get("/api/admin/modules").status_code == 401
    assert (
        client.get("/api/admin/modules", headers=_auth(SEED["user_id"])).status_code
        == 403
    )


def test_modules_reports_every_flag_with_current_values(monkeypatch):
    fake_settings = Settings(module_admin=True, module_fleet=True, module_tutorials=False)
    monkeypatch.setattr(admin_router_module, "get_settings", lambda: fake_settings)

    r = client.get("/api/admin/modules", headers=_auth(SEED["admin_id"]))
    assert r.status_code == 200
    body = r.json()

    # Une clé par flag, sans le préfixe module_, aucune ni en trop ni en moins.
    assert set(body.keys()) == {f.removeprefix("module_") for f in MODULE_FLAGS}
    assert body["admin"] is True
    assert body["fleet"] is True
    assert body["tutorials"] is False
