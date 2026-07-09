"""Preuve du chargement conditionnel des modules par tier (spike).

Chaque cas s'exécute dans un interpréteur frais (sous-process) car
`app.core.main` construit l'app et importe les modules au moment de l'import :
un seul process ne pourrait pas tester plusieurs tiers proprement.
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
    "security_header": "X-GitSky-Security" in health.headers,
    "analytics_status": c.get("/api/analytics/status").status_code,
    "agentic_status": c.get("/api/agent-services/status").status_code,
    "analytics_imported": "app.modules.analytics" in sys.modules,
    "agentic_imported": "app.modules.agentic" in sys.modules,
    "security_imported": "app.modules.security" in sys.modules,
}))
"""


def run(tier: str, **extra_env: str) -> dict:
    env = {**os.environ, "GITSKY_TIER": tier, "PYTHONPATH": str(BACKEND), **extra_env}
    out = subprocess.check_output(
        [sys.executable, "-c", SNIPPET], cwd=str(BACKEND), env=env, text=True
    )
    return json.loads(out.strip().splitlines()[-1])


def test_t0_loads_no_modules():
    r = run("t0")
    assert r["health"]["tier"] == "t0"
    # Endpoints des modules absents.
    assert r["analytics_status"] == 404
    assert r["agentic_status"] == 404
    assert r["security_header"] is False
    # Preuve clé : le code des modules désactivés n'est jamais importé.
    assert r["analytics_imported"] is False
    assert r["agentic_imported"] is False
    assert r["security_imported"] is False


def test_t2_loads_all_modules():
    r = run("t2")
    assert r["health"]["tier"] == "t2"
    assert r["analytics_status"] == 200
    assert r["agentic_status"] == 200
    assert r["security_header"] is True
    assert r["analytics_imported"] is True
    assert r["agentic_imported"] is True
    assert r["security_imported"] is True


def test_explicit_flag_overrides_tier_profile():
    # Tier T0 (tout désactivé) mais on force analytics via une variable d'env.
    r = run("t0", MODULE_ANALYTICS="true")
    assert r["health"]["tier"] == "t0"
    assert r["health"]["modules"]["analytics"] is True
    assert r["analytics_status"] == 200
    assert r["analytics_imported"] is True
    # Les autres modules restent au profil T0 (désactivés).
    assert r["agentic_imported"] is False
