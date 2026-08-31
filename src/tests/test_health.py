"""Endpoint /health avec vérification base (Phase 6, incr 4 — Chap 23 §4.1).

/health est la cible du monitoring de disponibilité (UptimeRobot). Avant cet
incrément il renvoyait tier + flags sans jamais toucher la base : un 200 avec
une base morte, incident invisible. Le Chap 23 exige un SELECT 1 et un 503 en
cas d'échec.

Le snippet du livre est synchrone (Session) ; le template est async — on porte
en async (adaptation fidèle, pas un écart). On injecte la session via
dependency_overrides pour piloter les deux chemins sans vraie base.
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import get_db  # noqa: E402
from app.core.main import app  # noqa: E402


class _FakeSession:
    """Session minimale : enregistre le SQL et échoue à la demande."""

    def __init__(self, *, fail: bool) -> None:
        self.fail = fail
        self.executed: list[str] = []

    async def execute(self, stmt):
        self.executed.append(str(stmt))
        if self.fail:
            raise RuntimeError("connexion base perdue")
        return None


def _client_with(session: _FakeSession) -> TestClient:
    async def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.pop(get_db, None)


def test_health_ok_runs_a_db_probe():
    session = _FakeSession(fail=False)
    resp = _client_with(session).get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    # Preuve que la vérif base a réellement eu lieu (pas juste un 200 de façade).
    assert any("SELECT 1" in sql for sql in session.executed)


def test_health_returns_503_when_db_is_down():
    session = _FakeSession(fail=True)
    resp = _client_with(session).get("/health")

    # UptimeRobot doit voir l'incident : base morte => 503, jamais 200.
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Database unavailable"


def test_health_still_reports_modules():
    # La charge utile existante (flags de modules) ne doit pas disparaître.
    session = _FakeSession(fail=False)
    body = _client_with(session).get("/health").json()
    assert "tier" not in body
    assert "modules" in body
    assert body["modules"]["auth"] is True


def test_health_reports_i18n_module(monkeypatch):
    # Bug de prod réel (cryptokilla, 2026-08-30) : le sélecteur de langue de
    # Navbar.tsx (`{modules.i18n && ...}`, round theming) ne pouvait jamais
    # s'afficher, sur AUCUN projet — MODULE_I18N=true dans .env, mais /health
    # ne l'a jamais renvoyé dans `modules`, contrairement à tous les autres
    # flags. `app/core/main.py` capture `settings = get_settings()` une
    # seule fois au niveau module (import) — patcher un `get_settings()`
    # frais est fragile selon l'ordre des tests : si un test antérieur
    # (ex. test_fleet_create_project.py) a déjà appelé
    # `get_settings.cache_clear()`, un nouveau `get_settings()` renvoie une
    # AUTRE instance que celle déjà liée dans main.py, et la mutation
    # n'atteint jamais le handler (reproduit en combinant les deux fichiers
    # de test). On patche donc directement l'objet que main.py utilise.
    from app.core import main as main_module

    monkeypatch.setattr(main_module.settings, "module_i18n", True)
    session = _FakeSession(fail=False)
    body = _client_with(session).get("/health").json()
    assert body["modules"]["i18n"] is True


def test_health_reports_leads_module(monkeypatch):
    # Meme classe de bug que i18n ci-dessus (round leads) : verrouille
    # l'entree /health pour chaque nouveau flag des sa creation.
    from app.core import main as main_module

    monkeypatch.setattr(main_module.settings, "module_leads", True)
    session = _FakeSession(fail=False)
    body = _client_with(session).get("/health").json()
    assert body["modules"]["leads"] is True
