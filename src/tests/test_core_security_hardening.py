"""Durcissements core issus du round sécurité ai-qube (2026-10-30).

1. secret_key par défaut — fail-closed : un démarrage en production qui garde
   la valeur dev (publique, visible dans ce repo) permettrait de forger un JWT
   valide. Même esprit que _forbid_stub_in_production (app.modules.monetization
   .stripe_client), appliqué au niveau du modèle Settings plutôt qu'au point
   d'usage : échoue à la construction, avant même que l'app FastAPI existe.

2. SecurityHeadersMiddleware — protège les réponses de l'API (pas la page HTML
   du frontend, couverte séparément par frontend/public/serve.json).
"""

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.core.security_headers import SecurityHeadersMiddleware  # noqa: E402


def test_settings_rejects_default_secret_key_in_production():
    with pytest.raises(RuntimeError):
        Settings(
            environment="production",
            secret_key="dev-insecure-change-me-in-production-0123456789",
        )


def test_settings_accepts_a_real_secret_key_in_production():
    # Ne doit rien lever.
    Settings(environment="production", secret_key="une-vraie-cle-secrete-random")


def test_settings_keeps_the_default_permissive_in_development():
    # Le dev reste permissif : pas de garde quand environment="development"
    # (valeur par défaut), sinon un `docker compose up` sans .env casserait.
    Settings()


def test_security_headers_present_on_every_response():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/ping")
    def ping() -> dict:
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/ping")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert (
        response.headers["Strict-Transport-Security"]
        == "max-age=63072000; includeSubDomains"
    )
