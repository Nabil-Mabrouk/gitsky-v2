"""POST /api/fleet/projects/{name}/github/create-repo et .../link-repo
(Chap 26, Phase D).

`create-repo` crée un dépôt via l'API GitHub puis tente d'y installer le
webhook push ; `link-repo` est le repli manuel (Chap 26 §lien manuel) pour un
dépôt qui existe déjà. Dans les deux cas, l'échec de l'installation du
webhook (droits admin manquants sur le dépôt, cas réaliste pour un dépôt
tiers) ne doit JAMAIS faire échouer la requête — le dépôt reste lié, le
webhook_installed passe à False, et un message explique le repli en redeploy
manuel. github_client.create_repo/create_webhook sont monkeypatchés : ce
fichier teste l'orchestration du router, pas le client HTTP GitHub lui-même
(couvert par test_github_client.py et test_failclosed_contract.py).
"""

import asyncio
import atexit
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.models  # noqa: E402,F401
import app.modules.fleet.models  # noqa: E402,F401
from app.core.auth.security import create_access_token, hash_password  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.models import User, UserRole  # noqa: E402
from app.modules.fleet import github_client  # noqa: E402
from app.modules.fleet import router as fleet_router  # noqa: E402

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_fleet_github_repo_{os.getpid()}.db"
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
app.include_router(fleet_router, prefix="/api/fleet")
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


def _register(name: str) -> None:
    r = client.post(
        "/api/fleet/projects/register",
        json={"name": name, "domain": f"{name}.mystudio.com"},
    )
    assert r.status_code == 200


def _fake_create_repo(full_name: str):
    owner, name = full_name.split("/", 1)

    async def _create_repo(project_name: str, private: bool = True) -> dict:
        assert project_name == name
        return {
            "full_name": full_name,
            "html_url": f"https://github.com/{full_name}",
            "clone_url": f"https://github.com/{full_name}.git",
        }

    return _create_repo


async def _ok_create_webhook(repo_full_name: str, webhook_url: str, secret: str) -> dict:
    return {"id": 1, "url": webhook_url}


async def _broken_create_webhook(repo_full_name: str, webhook_url: str, secret: str) -> dict:
    raise httpx.HTTPStatusError(
        "403 Forbidden", request=httpx.Request("POST", webhook_url), response=httpx.Response(403)
    )


async def _unconfigured_create_repo(project_name: str, private: bool = True) -> dict:
    # Contrat fail-closed réel de github_client.create_repo (FLEET_GITHUB_TOKEN
    # absent + ENVIRONMENT=production) : RuntimeError, pas httpx.HTTPError.
    raise RuntimeError(
        "FLEET_GITHUB_TOKEN manquant alors que ENVIRONMENT=production — "
        "refus du mode stub (fail-closed)"
    )


async def _unconfigured_create_webhook(repo_full_name: str, webhook_url: str, secret: str) -> dict:
    raise RuntimeError(
        "FLEET_GITHUB_TOKEN manquant alors que ENVIRONMENT=production — "
        "refus du mode stub (fail-closed)"
    )


def test_create_repo_requires_admin():
    _register("no-auth-project")
    assert (
        client.post("/api/fleet/projects/no-auth-project/github/create-repo", json={}).status_code
        == 401
    )
    assert (
        client.post(
            "/api/fleet/projects/no-auth-project/github/create-repo",
            json={},
            headers=_auth(SEED["user_id"]),
        ).status_code
        == 403
    )


def test_create_repo_unknown_project_is_404():
    r = client.post(
        "/api/fleet/projects/does-not-exist/github/create-repo",
        json={},
        headers=_auth(SEED["admin_id"]),
    )
    assert r.status_code == 404


def test_webhook_url_targets_api_subdomain_not_frontend():
    # Bug de prod réel : construite depuis settings.site_url (l'origine du
    # FRONTEND, Chap 10 SEO), l'URL du webhook atterrissait sur le routeur
    # Traefik du frontend (Host(`0-hitl.com`)) — jamais sur le backend
    # (Host(`api.0-hitl.com`), seul routeur qui expose réellement cette
    # route). GitHub rapportait pourtant "200 active" : le frontend renvoie
    # son index.html (SPA fallback) pour toute route inconnue, un faux
    # positif silencieux — même classe de bug que l'incident /leads (Chap 18).
    # `app.modules.fleet.__init__` fait `from .router import router` : ça
    # réécrit l'ATTRIBUT `app.modules.fleet.router` avec l'instance APIRouter
    # (même nom que le sous-module) — `import ... as` normal retombe donc
    # dessus. sys.modules, lui, garde la vraie référence au module (déjà
    # importé plus haut dans ce fichier via `from app.modules.fleet import
    # router as fleet_router`, qui importe le sous-module avant l'attribut).
    _router_module = sys.modules["app.modules.fleet.router"]

    class _FakeSettings:
        site_url = "https://0-hitl.com"

    url = _router_module._webhook_url(_FakeSettings(), "politique-ia")
    assert url == "https://api.0-hitl.com/api/fleet/webhooks/github/politique-ia"


def test_create_repo_success_installs_webhook_and_updates_project(monkeypatch):
    _register("with-webhook")
    monkeypatch.setattr(
        github_client, "create_repo", _fake_create_repo("acme-fleet/with-webhook")
    )
    monkeypatch.setattr(github_client, "create_webhook", _ok_create_webhook)

    r = client.post(
        "/api/fleet/projects/with-webhook/github/create-repo",
        json={"private": True},
        headers=_auth(SEED["admin_id"]),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["repo"] == "acme-fleet/with-webhook"
    assert body["html_url"] == "https://github.com/acme-fleet/with-webhook"
    assert body["webhook_installed"] is True
    assert body["message"] == ""

    grid = client.get(
        "/api/fleet/projects", headers=_auth(SEED["admin_id"])
    ).json()
    project = next(p for p in grid if p["name"] == "with-webhook")
    assert project["github_repo"] == "acme-fleet/with-webhook"
    assert project["github_webhook_installed"] is True


def test_create_repo_webhook_failure_still_links_repo_with_message(monkeypatch):
    _register("webhook-fails")
    monkeypatch.setattr(
        github_client, "create_repo", _fake_create_repo("acme-fleet/webhook-fails")
    )
    monkeypatch.setattr(github_client, "create_webhook", _broken_create_webhook)

    r = client.post(
        "/api/fleet/projects/webhook-fails/github/create-repo",
        json={},
        headers=_auth(SEED["admin_id"]),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["repo"] == "acme-fleet/webhook-fails"
    assert body["webhook_installed"] is False
    assert body["message"] != ""

    grid = client.get(
        "/api/fleet/projects", headers=_auth(SEED["admin_id"])
    ).json()
    project = next(p for p in grid if p["name"] == "webhook-fails")
    assert project["github_repo"] == "acme-fleet/webhook-fails"
    assert project["github_webhook_installed"] is False


def test_create_repo_not_configured_is_a_clean_503_not_a_500(monkeypatch):
    # Régression (27/08, prod) : cet endpoint n'attrapait rien du tout autour
    # de create_repo — un FLEET_GITHUB_TOKEN absent en production faisait
    # planter la requête en 500 non géré plutôt qu'un 503 explicite (même
    # famille de fail-closed que generator_client.GeneratorNotConfigured,
    # Chap 27).
    _register("token-missing")
    monkeypatch.setattr(github_client, "create_repo", _unconfigured_create_repo)

    r = client.post(
        "/api/fleet/projects/token-missing/github/create-repo",
        json={},
        headers=_auth(SEED["admin_id"]),
    )
    assert r.status_code == 503
    assert "FLEET_GITHUB_TOKEN" in r.json()["detail"]


def test_link_repo_webhook_not_configured_still_links_with_message(monkeypatch):
    # Même régression que ci-dessus, côté _install_webhook cette fois : un
    # jeton absent lève RuntimeError, pas httpx.HTTPError.
    _register("link-webhook-not-configured")
    monkeypatch.setattr(github_client, "create_webhook", _unconfigured_create_webhook)

    r = client.post(
        "/api/fleet/projects/link-webhook-not-configured/github/link-repo",
        json={"repo": "someone/existing-repo"},
        headers=_auth(SEED["admin_id"]),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["repo"] == "someone/existing-repo"
    assert body["webhook_installed"] is False
    assert "FLEET_GITHUB_TOKEN" in body["message"]


def test_link_repo_requires_admin():
    _register("link-no-auth")
    assert (
        client.post(
            "/api/fleet/projects/link-no-auth/github/link-repo",
            json={"repo": "someone/existing"},
        ).status_code
        == 401
    )


def test_link_repo_unknown_project_is_404():
    r = client.post(
        "/api/fleet/projects/does-not-exist/github/link-repo",
        json={"repo": "someone/existing"},
        headers=_auth(SEED["admin_id"]),
    )
    assert r.status_code == 404


def test_link_repo_success_installs_webhook(monkeypatch):
    _register("link-me")
    monkeypatch.setattr(github_client, "create_webhook", _ok_create_webhook)

    r = client.post(
        "/api/fleet/projects/link-me/github/link-repo",
        json={"repo": "someone/existing-repo"},
        headers=_auth(SEED["admin_id"]),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["repo"] == "someone/existing-repo"
    assert body["html_url"] == "https://github.com/someone/existing-repo"
    assert body["webhook_installed"] is True


def test_link_repo_webhook_failure_still_links_with_message(monkeypatch):
    _register("link-me-fails")
    monkeypatch.setattr(github_client, "create_webhook", _broken_create_webhook)

    r = client.post(
        "/api/fleet/projects/link-me-fails/github/link-repo",
        json={"repo": "third-party/repo-without-admin-rights"},
        headers=_auth(SEED["admin_id"]),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["repo"] == "third-party/repo-without-admin-rights"
    assert body["webhook_installed"] is False
    assert "webhook" in body["message"].lower()
