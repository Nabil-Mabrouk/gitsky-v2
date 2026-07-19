"""Token de lecture des stats du landing collector (durcissement, arbitrage 4.4).

GET /leads/{project}/stats était public : le funnel (nombre de signups) de
n'importe quel projet de la flotte fuyait à quiconque joint le collector. Même
sémantique que le token fleet :

- COLLECTOR_STATS_TOKEN configuré -> header X-Collector-Token obligatoire ;
- absent -> ouvert en dev, REFUS (503) si ENVIRONMENT=production (fail-closed).

POST /leads reste public par conception (les landings T0 y postent sans secret).
"""

import asyncio
import atexit
import os
import sys
import tempfile
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "shared_services"
sys.path.insert(0, str(SHARED))

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_landing_tok_{os.getpid()}.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()
os.environ["LANDING_DB_URL"] = f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402

from landing_collector.database import create_tables, engine  # noqa: E402
from landing_collector.main import app  # noqa: E402

asyncio.run(create_tables())
client = TestClient(app)


@atexit.register
def _cleanup() -> None:
    asyncio.run(engine.dispose())
    try:
        _DB_FILE.unlink()
    except OSError:
        pass


def test_stats_require_token_when_configured(monkeypatch):
    monkeypatch.setenv("COLLECTOR_STATS_TOKEN", "s3cret-stats")

    assert client.get("/leads/p/stats").status_code == 401
    assert (
        client.get("/leads/p/stats", headers={"X-Collector-Token": "faux"}).status_code
        == 401
    )
    r = client.get("/leads/p/stats", headers={"X-Collector-Token": "s3cret-stats"})
    assert r.status_code == 200


def test_stats_fail_closed_in_production_without_token(monkeypatch):
    monkeypatch.delenv("COLLECTOR_STATS_TOKEN", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert client.get("/leads/p/stats").status_code == 503


def test_stats_open_in_dev_without_token(monkeypatch):
    monkeypatch.delenv("COLLECTOR_STATS_TOKEN", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert client.get("/leads/p/stats").status_code == 200


def test_lead_capture_stays_public(monkeypatch):
    # Les landings T0 postent sans secret : la capture ne doit jamais exiger
    # de token, même quand la lecture des stats est verrouillée.
    monkeypatch.setenv("COLLECTOR_STATS_TOKEN", "s3cret-stats")
    r = client.post("/leads", json={"project": "p", "email": "a@b.com"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
