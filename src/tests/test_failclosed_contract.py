"""Contrat fail-closed des intégrations externes (durcissement).

Le patron « stub déterministe si la clé manque » (stripe, llm, suno, studio)
est idéal en dev/test mais dangereux en production : un secret oublié faisait
retomber silencieusement sur le stub — pire cas, le webhook Stripe acceptait
des événements FORGÉS (fulfillment gratuit, passage premium arbitraire).

Contrat, pour TOUTE intégration présente et à venir :
- ENVIRONMENT=production + secret absent -> lever (RuntimeError), jamais le stub ;
- en dev (ENVIRONMENT non-production), le stub reste le comportement nominal.

Le webhook Stripe est aussi vérifié au niveau HTTP : 503 en prod sans secret.
"""

import asyncio
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1]
BACKEND = SRC / "generator" / "template"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(SRC / "shared_services"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core import mailer  # noqa: E402
from app.modules.agentic.llm_client import call_llm  # noqa: E402
from app.modules.agentic.tools.suno import suno_generate  # noqa: E402
from app.modules.fleet import github_client  # noqa: E402
from app.modules.fleet.landing_collector_client import fetch_leads  # noqa: E402
from app.modules.monetization.router import shop_router  # noqa: E402
from landing_collector import mailer as landing_collector_mailer  # noqa: E402
from app.modules.monetization.stripe_client import (  # noqa: E402
    create_checkout_session,
    verify_webhook,
)
from studio.image import generate_image as studio_generate_image  # noqa: E402
from studio.llm import generate as studio_generate  # noqa: E402

_MESSAGES = [{"role": "user", "content": "ping"}]

# (nom, callable sans configuration, variables de config à purger)
INTEGRATIONS = [
    (
        "stripe_checkout",
        lambda: create_checkout_session("pack", "a@b.com"),
        ["STRIPE_SECRET_KEY"],
    ),
    (
        "stripe_webhook",
        lambda: verify_webhook(b"{}", None, ""),
        ["STRIPE_WEBHOOK_SECRET"],
    ),
    ("llm_client", lambda: call_llm("m", _MESSAGES), ["LLM_PROXY_URL"]),
    (
        "suno",
        lambda: asyncio.run(suno_generate({"parameters": {}}, {})),
        ["SUNO_API_KEY"],
    ),
    (
        "studio_llm",
        lambda: studio_generate("m", "prompt", stub=lambda: {"ok": True}),
        ["LLM_PROXY_URL"],
    ),
    (
        "studio_image",
        lambda: studio_generate_image("prompt"),
        # Réutilise LLM_PROXY_URL plutôt qu'une variable dédiée : même
        # llm-proxy que studio_llm, juste un modèle différent (gpt-image-2)
        # dans le même litellm-config.yaml — un seul point de config à gérer.
        ["LLM_PROXY_URL"],
    ),
    (
        "mailer",
        lambda: mailer.send_email("a@b.com", "s", "b"),
        ["SMTP_HOST"],
    ),
    (
        "fleet_leads",
        lambda: asyncio.run(fetch_leads("p")),
        ["LANDING_COLLECTOR_URL"],
    ),
    (
        "landing_collector_mailer",
        lambda: landing_collector_mailer.send_email("a@b.com", "s", "b"),
        ["SMTP_HOST"],
    ),
    (
        "fleet_github_create_repo",
        lambda: asyncio.run(github_client.create_repo("p")),
        ["FLEET_GITHUB_TOKEN"],
    ),
    (
        "fleet_github_create_webhook",
        lambda: asyncio.run(github_client.create_webhook("o/r", "https://x/webhook", "s")),
        ["FLEET_GITHUB_TOKEN"],
    ),
]


@pytest.mark.parametrize("name,call,secret_vars", INTEGRATIONS, ids=[i[0] for i in INTEGRATIONS])
def test_production_without_secret_raises(name, call, secret_vars, monkeypatch):
    for var in secret_vars:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(RuntimeError):
        call()


@pytest.mark.parametrize("name,call,secret_vars", INTEGRATIONS, ids=[i[0] for i in INTEGRATIONS])
def test_dev_without_secret_still_stubs(name, call, secret_vars, monkeypatch):
    for var in secret_vars:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    # Ne doit PAS lever : le stub est le comportement nominal du dev.
    call()


# --- Niveau HTTP : le webhook répond 503, l'événement n'est pas traité ------

def test_webhook_route_returns_503_in_production_without_secret(monkeypatch):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    app = FastAPI()
    app.include_router(shop_router, prefix="/api/shop")
    client = TestClient(app)

    r = client.post(
        "/api/shop/webhook",
        json={"type": "checkout.session.completed", "data": {"object": {"id": "cs_x"}}},
    )
    assert r.status_code == 503
