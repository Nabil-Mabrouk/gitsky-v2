"""Client GitHub — dépôt et webhook (Chap 26, Phase D).

Contrat fail-closed déjà couvert par test_failclosed_contract.py (prod sans
FLEET_GITHUB_TOKEN -> RuntimeError). Ce fichier vérifie la forme exacte du
stub dev déterministe (id/urls prévisibles, aucun appel réseau) — c'est ce
que router.py assemble dans GithubRepoResult, donc sa forme compte.
"""

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from app.modules.fleet import github_client  # noqa: E402


def test_create_repo_stub_without_org(monkeypatch):
    monkeypatch.delenv("FLEET_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("FLEET_GITHUB_ORG", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    repo = asyncio.run(github_client.create_repo("pain-scraper"))

    assert repo == {
        "full_name": "stub-owner/pain-scraper",
        "html_url": "https://github.test/stub-owner/pain-scraper",
        "clone_url": "https://github.test/stub-owner/pain-scraper.git",
    }


def test_create_repo_stub_uses_configured_org(monkeypatch):
    monkeypatch.delenv("FLEET_GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("FLEET_GITHUB_ORG", "acme-fleet")
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    repo = asyncio.run(github_client.create_repo("pain-scraper"))

    assert repo["full_name"] == "acme-fleet/pain-scraper"


def test_create_webhook_stub_returns_the_requested_url(monkeypatch):
    monkeypatch.delenv("FLEET_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    hook = asyncio.run(
        github_client.create_webhook(
            "acme-fleet/pain-scraper", "https://mystudio.com/api/fleet/webhooks/github/pain-scraper", "s3cret"
        )
    )

    assert hook == {
        "id": 0,
        "url": "https://mystudio.com/api/fleet/webhooks/github/pain-scraper",
    }
