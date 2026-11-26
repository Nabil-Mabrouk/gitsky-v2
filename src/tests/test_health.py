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


# --- Umami (Chap 13 §« Mesure d'Audience », 2026-11-26) ----------------------
#
# Le frontend lit déjà /health (nom, modules) : il y trouve aussi la config du
# script de suivi Umami, posée dans .env.local — à l'exécution, sans rebuild.
# Clé ABSENTE tant que la config n'est pas complète et valide : un projet non
# branché ne charge aucun script.

_WEBSITE_ID = "4f6c1b2a-9d3e-4c5f-8a7b-0123456789ab"


def _health_with_umami(monkeypatch, *, script_url: str, website_id: str,
                       site_url: str = "https://f-ynd.com") -> dict:
    from app.core import main as main_module

    monkeypatch.setattr(main_module.settings, "umami_script_url", script_url)
    monkeypatch.setattr(main_module.settings, "umami_website_id", website_id)
    monkeypatch.setattr(main_module.settings, "site_url", site_url)
    return _client_with(_FakeSession(fail=False)).get("/health").json()


def test_health_exposes_umami_config_when_set(monkeypatch):
    body = _health_with_umami(monkeypatch, script_url="https://stats.0-hitl.com/s.js",
                              website_id=_WEBSITE_ID)
    assert body["umami"] == {
        "script_url": "https://stats.0-hitl.com/s.js",
        "website_id": _WEBSITE_ID,
        # Le script ne mesure que sur le vrai domaine du projet (data-domains) :
        # jamais depuis le dev local ni une copie du site.
        "domains": "f-ynd.com",
    }


def test_health_omits_umami_when_not_configured(monkeypatch):
    body = _health_with_umami(monkeypatch, script_url="", website_id="")
    assert "umami" not in body


def test_health_omits_umami_when_partially_configured(monkeypatch):
    body = _health_with_umami(monkeypatch, script_url="https://stats.0-hitl.com/s.js",
                              website_id="")
    assert "umami" not in body


def test_health_rejects_non_https_or_malformed_umami_values(monkeypatch):
    # Valeurs injectées telles quelles dans une balise <script> du navigateur :
    # toute valeur douteuse est ignorée plutôt que servie.
    for script_url, website_id in [
        ("http://stats.0-hitl.com/s.js", _WEBSITE_ID),
        ("javascript:alert(1)", _WEBSITE_ID),
        ("https://stats.0-hitl.com/s.js", "pas-un-uuid"),
        ("https://stats.0-hitl.com/s.js", _WEBSITE_ID + '" onload="x'),
    ]:
        body = _health_with_umami(monkeypatch, script_url=script_url, website_id=website_id)
        assert "umami" not in body, (script_url, website_id)
