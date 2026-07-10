"""Landing collector (Phase 4, services partagés — Chap 18).

Service autonome : une landing poste un lead, le fleet lit les stats du projet.
Base SQLite fichier via LANDING_DB_URL (fixé avant import).
"""

import asyncio
import atexit
import os
import sys
import tempfile
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "shared_services"
sys.path.insert(0, str(SHARED))

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_landing_{os.getpid()}.db"
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


def test_collect_leads_and_read_project_stats():
    assert client.post(
        "/leads", json={"project": "pain-scraper", "email": "a@b.com"}
    ).json() == {"ok": True}
    client.post(
        "/leads",
        json={"project": "pain-scraper", "email": "c@d.com", "source": "reddit"},
    )
    client.post("/leads", json={"project": "other-idea", "email": "e@f.com"})

    # Le fleet dashboard lit le funnel : 2 signups pour pain-scraper.
    r = client.get("/leads/pain-scraper/stats")
    assert r.status_code == 200
    assert r.json() == {"project": "pain-scraper", "signups": 2}

    # Projet sans lead -> 0 (pas d'erreur).
    assert client.get("/leads/inconnu/stats").json()["signups"] == 0


def test_invalid_email_rejected():
    r = client.post("/leads", json={"project": "x", "email": "pas-un-email"})
    assert r.status_code == 422
