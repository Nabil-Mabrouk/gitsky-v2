"""POST /api/fleet/projects et GET /api/fleet/module-catalog (Chap 27, Phase E).

Le wizard de création orchestre trois clients déjà testés isolément
(generator_client, github_client, git_client) — ce fichier vérifie
l'orchestration du router : ordre des opérations, ce qui est fatal (nom
invalide, projet déjà enregistré, générateur non configuré) contre ce qui est
best-effort et journalisé en warning (échec GitHub, échec du premier push),
et le bootstrap du tout premier `deploy_triggered` quand le webhook n'a pas pu
être installé. generator_client.generate_project / github_client.* /
git_client.push_initial_commit sont monkeypatchés : la génération réelle est
couverte par test_generator_client.py, le push réel par test_git_client.py.
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
from app.core.config import get_settings  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.models import User, UserRole  # noqa: E402
from app.modules.fleet import generator_client, git_client, github_client  # noqa: E402
from app.modules.fleet import router as fleet_router  # noqa: E402

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_fleet_create_project_{os.getpid()}.db"
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


def _fake_generate(tmp_path: Path):
    def _gen(name: str, config: dict, dest_root: Path) -> Path:
        dest = tmp_path / name
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    return _gen


async def _ok_create_webhook(repo_full_name: str, webhook_url: str, secret: str) -> dict:
    return {"id": 1, "url": webhook_url}


async def _broken_create_webhook(repo_full_name: str, webhook_url: str, secret: str) -> dict:
    raise httpx.HTTPStatusError(
        "403", request=httpx.Request("POST", webhook_url), response=httpx.Response(403)
    )


async def _fake_create_repo(name: str, private: bool = True) -> dict:
    return {
        "full_name": f"acme-fleet/{name}",
        "html_url": f"https://github.com/acme-fleet/{name}",
        "clone_url": f"https://github.com/acme-fleet/{name}.git",
    }


async def _broken_create_repo(name: str, private: bool = True) -> dict:
    raise httpx.HTTPStatusError(
        "422", request=httpx.Request("POST", "https://api.github.com/user/repos"), response=httpx.Response(422)
    )


async def _unconfigured_create_repo(name: str, private: bool = True) -> dict:
    # Reproduit le contrat fail-closed réel de github_client.create_repo
    # (FLEET_GITHUB_TOKEN absent + ENVIRONMENT=production) : RuntimeError, pas
    # httpx.HTTPError — bug de prod du 27/08 (Chap 27) où ce cas n'était pas
    # attrapé et faisait 500 toute la requête au lieu d'un warning.
    raise RuntimeError(
        "FLEET_GITHUB_TOKEN manquant alors que ENVIRONMENT=production — "
        "refus du mode stub (fail-closed)"
    )


def test_module_catalog_requires_admin_and_lists_short_flags():
    assert client.get("/api/fleet/module-catalog").status_code == 401
    r = client.get("/api/fleet/module-catalog", headers=_auth(SEED["admin_id"]))
    assert r.status_code == 200
    catalog = r.json()
    assert "admin" in catalog
    assert "fleet" in catalog
    assert "module_admin" not in catalog  # clés courtes, sans préfixe
    assert "auth" not in catalog  # core, jamais un choix (Chap 2 §1)


def test_create_project_requires_admin():
    r = client.post(
        "/api/fleet/projects", json={"name": "no-auth-create", "modules": {}}
    )
    assert r.status_code == 401
    r = client.post(
        "/api/fleet/projects",
        json={"name": "no-auth-create", "modules": {}},
        headers=_auth(SEED["user_id"]),
    )
    assert r.status_code == 403


def test_create_project_rejects_invalid_name():
    r = client.post(
        "/api/fleet/projects",
        json={"name": "Not A Valid Slug", "modules": {}},
        headers=_auth(SEED["admin_id"]),
    )
    assert r.status_code == 400


def test_create_project_link_mode_requires_repo():
    r = client.post(
        "/api/fleet/projects",
        json={"name": "link-without-repo", "modules": {}, "github_mode": "link"},
        headers=_auth(SEED["admin_id"]),
    )
    assert r.status_code == 400


def test_create_project_conflicts_with_existing_registration(monkeypatch, tmp_path):
    monkeypatch.setattr(generator_client, "generate_project", _fake_generate(tmp_path))
    client.post(
        "/api/fleet/projects",
        json={"name": "already-there", "modules": {}},
        headers=_auth(SEED["admin_id"]),
    )
    r2 = client.post(
        "/api/fleet/projects",
        json={"name": "already-there", "modules": {}},
        headers=_auth(SEED["admin_id"]),
    )
    assert r2.status_code == 409


def test_create_project_returns_503_when_generator_not_configured(monkeypatch):
    def _raise(name, config, dest_root):
        raise generator_client.GeneratorNotConfigured("GITSKY_GENERATOR_PATH non configuré")

    monkeypatch.setattr(generator_client, "generate_project", _raise)
    r = client.post(
        "/api/fleet/projects",
        json={"name": "generator-down", "modules": {}},
        headers=_auth(SEED["admin_id"]),
    )
    assert r.status_code == 503


def test_create_project_skip_github_registers_with_fleet_subdomain(monkeypatch, tmp_path):
    monkeypatch.setattr(generator_client, "generate_project", _fake_generate(tmp_path))
    r = client.post(
        "/api/fleet/projects",
        json={"name": "skip-github", "modules": {"admin": True}},
        headers=_auth(SEED["admin_id"]),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["generated"] is True
    assert body["github_repo"] is None
    assert body["webhook_installed"] is False
    assert body["pushed"] is False
    assert body["deploy_triggered"] is False
    assert body["warnings"] == []
    assert body["project"]["domain"] == "skip-github.mystudio.com"
    assert body["project"]["status"] == "active"


def test_create_project_without_domain_uses_configured_subdomain_suffix(monkeypatch, tmp_path):
    # Régression (27/08, prod) : le suffixe par défaut était codé en dur
    # (publish.FLEET_SUBDOMAIN_SUFFIX) — un déploiement réel qui règle
    # FLEET_SUBDOMAIN_SUFFIX dans son .env doit voir ce réglage EFFECTIVEMENT
    # utilisé par le wizard, pas seulement par publish.evaluate_promotion.
    monkeypatch.setattr(generator_client, "generate_project", _fake_generate(tmp_path))
    monkeypatch.setenv("FLEET_SUBDOMAIN_SUFFIX", ".0-hitl.com")
    get_settings.cache_clear()
    try:
        r = client.post(
            "/api/fleet/projects",
            json={"name": "real-domain", "modules": {}},
            headers=_auth(SEED["admin_id"]),
        )
        assert r.status_code == 201
        assert r.json()["project"]["domain"] == "real-domain.0-hitl.com"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_create_project_with_github_create_and_successful_push(monkeypatch, tmp_path):
    monkeypatch.setattr(generator_client, "generate_project", _fake_generate(tmp_path))
    monkeypatch.setattr(github_client, "create_repo", _fake_create_repo)
    monkeypatch.setattr(github_client, "create_webhook", _ok_create_webhook)
    monkeypatch.setattr(
        git_client, "push_initial_commit", lambda project_dir, remote_url, branch: None
    )

    r = client.post(
        "/api/fleet/projects",
        json={"name": "full-happy-path", "modules": {}, "github_mode": "create"},
        headers=_auth(SEED["admin_id"]),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["github_repo"] == "acme-fleet/full-happy-path"
    assert body["webhook_installed"] is True
    assert body["pushed"] is True
    # Webhook réel installé : GitHub notifiera lui-même, pas de bootstrap.
    assert body["deploy_triggered"] is False
    assert body["warnings"] == []


def test_create_project_bootstraps_deploy_triggered_when_webhook_install_fails(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(generator_client, "generate_project", _fake_generate(tmp_path))
    monkeypatch.setattr(github_client, "create_repo", _fake_create_repo)
    monkeypatch.setattr(github_client, "create_webhook", _broken_create_webhook)
    monkeypatch.setattr(
        git_client, "push_initial_commit", lambda project_dir, remote_url, branch: None
    )

    r = client.post(
        "/api/fleet/projects",
        json={"name": "webhook-fails-bootstrap", "modules": {}, "github_mode": "create"},
        headers=_auth(SEED["admin_id"]),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["webhook_installed"] is False
    assert body["pushed"] is True
    assert body["deploy_triggered"] is True
    assert any("webhook" in w.lower() for w in body["warnings"])


def test_create_project_push_failure_is_a_warning_not_a_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(generator_client, "generate_project", _fake_generate(tmp_path))
    monkeypatch.setattr(github_client, "create_webhook", _ok_create_webhook)

    def _broken_push(project_dir, remote_url, branch):
        raise RuntimeError("no network")

    monkeypatch.setattr(git_client, "push_initial_commit", _broken_push)

    r = client.post(
        "/api/fleet/projects",
        json={
            "name": "push-fails",
            "modules": {},
            "github_mode": "link",
            "github_repo": "third-party/existing",
        },
        headers=_auth(SEED["admin_id"]),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["github_repo"] == "third-party/existing"
    assert body["pushed"] is False
    assert body["deploy_triggered"] is False
    assert any("push" in w.lower() for w in body["warnings"])


def test_create_project_github_repo_creation_failure_is_a_warning_not_a_failure(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(generator_client, "generate_project", _fake_generate(tmp_path))
    monkeypatch.setattr(github_client, "create_repo", _broken_create_repo)

    r = client.post(
        "/api/fleet/projects",
        json={"name": "repo-creation-fails", "modules": {}, "github_mode": "create"},
        headers=_auth(SEED["admin_id"]),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["generated"] is True
    assert body["github_repo"] is None
    assert body["pushed"] is False
    assert len(body["warnings"]) == 1


def test_create_project_github_not_configured_is_a_warning_not_a_500(monkeypatch, tmp_path):
    # Régression (27/08, prod) : FLEET_GITHUB_TOKEN absent en production fait
    # lever RuntimeError (fail-closed) à github_client.create_repo, pas
    # httpx.HTTPError — un except trop étroit laissait ça remonter en 500 non
    # attrapé, alors que Chap 27 promet qu'à partir de l'étape 3 (génération +
    # enregistrement faits), plus rien n'est fatal.
    monkeypatch.setattr(generator_client, "generate_project", _fake_generate(tmp_path))
    monkeypatch.setattr(github_client, "create_repo", _unconfigured_create_repo)

    r = client.post(
        "/api/fleet/projects",
        json={"name": "github-token-missing", "modules": {}, "github_mode": "create"},
        headers=_auth(SEED["admin_id"]),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["generated"] is True
    assert body["github_repo"] is None
    assert body["pushed"] is False
    assert any("FLEET_GITHUB_TOKEN" in w for w in body["warnings"])
