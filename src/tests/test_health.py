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
