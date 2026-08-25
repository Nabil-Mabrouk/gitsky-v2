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

from landing_collector import mailer  # noqa: E402
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


def test_list_leads_sorted_desc_and_isolated_by_project():
    client.post("/leads", json={"project": "list-a", "email": "1@a.com"})
    client.post(
        "/leads", json={"project": "list-a", "email": "2@a.com", "source": "reddit"}
    )
    client.post("/leads", json={"project": "list-b", "email": "3@b.com"})

    r = client.get("/leads/list-a")
    assert r.status_code == 200
    body = r.json()
    assert [lead["email"] for lead in body] == ["2@a.com", "1@a.com"]
    assert body[0]["source"] == "reddit"

    # Isolation par projet : list-b n'apparaît pas dans list-a.
    assert all(lead["project"] == "list-a" for lead in body)


def test_list_leads_empty_project_returns_empty_list():
    assert client.get("/leads/inconnu-list").json() == []


def test_capture_with_domain_sends_confirmation_email_and_stores_unverified(monkeypatch):
    sent: dict = {}

    def fake_send_email(to: str, subject: str, body: str) -> None:
        sent["to"] = to
        sent["body"] = body

    monkeypatch.setattr(mailer, "send_email", fake_send_email)

    client.post(
        "/leads",
        json={"project": "optin-a", "email": "opt@x.com", "domain": "optin-a.example.com"},
    )

    assert sent["to"] == "opt@x.com"
    assert "https://optin-a.example.com/leads/verify/" in sent["body"]

    leads = client.get("/leads/optin-a").json()
    assert leads[0]["verified"] is False


def test_verify_token_marks_lead_verified_and_is_single_use(monkeypatch):
    sent: dict = {}

    def fake_send_email(to: str, subject: str, body: str) -> None:
        sent["body"] = body

    monkeypatch.setattr(mailer, "send_email", fake_send_email)

    client.post(
        "/leads",
        json={"project": "optin-b", "email": "verify@x.com", "domain": "optin-b.example.com"},
    )
    token = sent["body"].split("/leads/verify/")[1].split("\n")[0]

    r = client.get(f"/leads/verify/{token}")
    assert r.status_code == 200
    assert "confirmé" in r.text

    leads = client.get("/leads/optin-b").json()
    assert leads[0]["verified"] is True

    # Rejoué : le jeton a été consommé (verify_token remis à None).
    replay = client.get(f"/leads/verify/{token}")
    assert replay.status_code == 404
    assert "invalide" in replay.text


def test_verify_unknown_token_returns_generic_invalid_page():
    r = client.get("/leads/verify/does-not-exist")
    assert r.status_code == 404
    assert "invalide" in r.text


def test_duplicate_capture_same_project_email_does_not_resend(monkeypatch):
    calls = []
    monkeypatch.setattr(mailer, "send_email", lambda **kw: calls.append(kw))

    payload = {"project": "optin-c", "email": "dup@x.com", "domain": "optin-c.example.com"}
    client.post("/leads", json=payload)
    client.post("/leads", json=payload)
    client.post("/leads", json=payload)

    assert len(calls) == 1
    leads = client.get("/leads/optin-c").json()
    assert len(leads) == 1
