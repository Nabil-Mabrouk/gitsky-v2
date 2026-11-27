"""Preuve du chargement conditionnel des modules (spike, Chap 2/3).

Chaque cas s'exécute dans un interpréteur frais (sous-process) car
`app.core.main` construit l'app et importe les modules au moment de l'import :
un seul process ne pourrait pas tester plusieurs combinaisons de flags
proprement.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"

# Exécuté dans le sous-process : monte l'app, interroge les endpoints, et
# rapporte ce qui a réellement été importé.
SNIPPET = r"""
import json, sys
from fastapi.testclient import TestClient
from app.core.main import app

c = TestClient(app)
health = c.get("/health")
print(json.dumps({
    "health": health.json(),
    "analytics_status": c.get("/api/admin/analytics/world").status_code,
    "admin_status": c.get("/api/admin/modules").status_code,
    "agentic_status": c.get("/api/agent-services/services").status_code,
    "worker_status": c.get("/api/worker/status").status_code,
    "admin_imported": "app.modules.admin" in sys.modules,
    "agentic_imported": "app.modules.agentic" in sys.modules,
    "security_imported": "app.modules.security" in sys.modules,
    "worker_imported": "app.modules.worker" in sys.modules,
}))
"""


def run(**module_env: str) -> dict:
    env = {**os.environ, "PYTHONPATH": str(BACKEND), **module_env}
    out = subprocess.check_output(
        [sys.executable, "-c", SNIPPET], cwd=str(BACKEND), env=env, text=True
    )
    return json.loads(out.strip().splitlines()[-1])


def test_no_modules_active_by_default():
    r = run()
    # auth reste actif (core) : ce n'est pas un flag MODULE_*.
    assert r["health"]["modules"]["auth"] is True
    assert r["health"]["modules"]["admin"] is False
    # Endpoints des modules absents.
    assert r["admin_status"] == 404
    assert r["analytics_status"] == 404
    assert r["agentic_status"] == 404
    assert r["worker_status"] == 404
    # Preuve clé : le code des modules désactivés n'est jamais importé.
    assert r["admin_imported"] is False
    assert r["agentic_imported"] is False
    assert r["security_imported"] is False
    assert r["worker_imported"] is False


def test_all_flags_active_loads_every_module():
    r = run(
        MODULE_ADMIN="true",
        MODULE_SECURITY_MIDDLEWARE="true",
        MODULE_AGENTIC="true",
        MODULE_TUTORIALS="true",
        MODULE_ONBOARDING="true",
        MODULE_MONETIZATION_SHOP="true",
        MODULE_MONETIZATION_SUBSCRIPTION="true",
        MODULE_WORKER="true",
    )
    assert r["health"]["modules"]["admin"] is True
    assert r["admin_status"] == 401  # monté mais protégé (require_admin)
    assert r["agentic_status"] == 200
    assert r["worker_status"] == 401  # monté mais protégé (require_admin)
    assert r["admin_imported"] is True
    assert r["agentic_imported"] is True
    assert r["security_imported"] is True
    assert r["worker_imported"] is True


def test_a_single_flag_activates_only_that_module():
    # Aucun profil, aucune dérivation : activer admin seul ne doit rien
    # entraîner d'autre.
    r = run(MODULE_ADMIN="true")
    assert r["health"]["modules"]["admin"] is True
    assert r["admin_status"] == 401  # monté (flag) mais protégé admin
    assert r["admin_imported"] is True
    # Les autres modules restent inactifs : pas de profil qui les entraînerait.
    assert r["agentic_imported"] is False
    assert r["health"]["modules"]["agentic"] is False


def test_retired_analytics_module_stays_gone():
    # Module analytics maison retiré le 2026-11-27 au profit d'Umami (Chap 13).
    # Un vieux .env qui contient encore MODULE_ANALYTICS=true ne doit ni
    # planter l'app (extra="ignore") ni remonter l'ancien endpoint.
    r = run(MODULE_ANALYTICS="true", MODULE_ADMIN="true")
    assert "analytics" not in r["health"]["modules"]
    assert r["analytics_status"] == 404
