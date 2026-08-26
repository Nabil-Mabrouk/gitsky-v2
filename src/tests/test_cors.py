"""CORS du châssis (durcissement) — contrat frontend <-> API.

Le frontend vit sur une autre origine que l'API (localhost:5173 -> :8000 en dev,
domaine.com -> api.domaine.com en prod) et envoie `credentials: "include"`. Sans
CORSMiddleware, le navigateur bloque tout le flux d'auth — les tests TestClient
ne le voient pas (pas de same-origin policy), d'où ce contrat explicite :

1. le preflight de l'origine frontend passe, credentials autorisés ;
2. une origine inconnue ne reçoit aucun en-tête CORS ;
3. la liste d'origines reste alignée sur `settings.frontend_url` (protège
   contre une suppression ou un « allow_origins=["*"] » accidentels —
   « * » est incompatible avec les cookies de refresh).
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.main import app  # noqa: E402

client = TestClient(app)
FRONTEND = get_settings().frontend_url


def _preflight(origin: str):
    # Le preflight est intercepté par CORSMiddleware avant le routage : la
    # route n'a même pas besoin d'exister (même si auth, core, la monte
    # toujours).
    return client.options(
        "/api/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )


def test_preflight_accepts_frontend_origin():
    r = _preflight(FRONTEND)
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == FRONTEND
    # Indispensable au cookie refresh (credentials: "include" côté frontend).
    assert r.headers["access-control-allow-credentials"] == "true"


def test_preflight_rejects_unknown_origin():
    r = _preflight("https://attaquant.example")
    assert "access-control-allow-origin" not in r.headers


def test_cors_config_follows_frontend_url_setting():
    cors = [m for m in app.user_middleware if m.cls is CORSMiddleware]
    assert cors, "CORSMiddleware absent de app.core.main — le frontend ne peut plus appeler l'API"
    kwargs = cors[0].kwargs
    assert kwargs["allow_origins"] == [FRONTEND]
    assert kwargs["allow_credentials"] is True
