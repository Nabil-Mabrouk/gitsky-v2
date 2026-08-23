"""app.core.http.real_client_ip — extraction de l'IP client derrière Traefik.

Bug réel (dashboard Sécurité, premier vrai déploiement) : les deux
middlewares (security, analytics) lisaient request.client.host, qui est
l'IP de Traefik lui-même (le backend n'est jamais joignable directement).
Testé ici en isolation (fonction pure) ; les deux middlewares ont chacun
leur propre test d'intégration (test_security_runtime.py, test_analytics.py).
"""

import sys
from pathlib import Path
from unittest.mock import Mock

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from app.core.http import real_client_ip  # noqa: E402


def _request(headers: dict[str, str], client_host: str | None = "172.18.0.2"):
    req = Mock()
    req.headers = headers
    req.client = Mock(host=client_host) if client_host else None
    return req


def test_uses_last_x_forwarded_for_entry_not_first():
    # Traefik ajoute son IP à LA FIN de la liste ; un client peut forger le
    # reste — faire confiance au premier maillon permettrait un spoof trivial.
    req = _request({"x-forwarded-for": "1.2.3.4, 9.9.9.9"})
    assert real_client_ip(req) == "9.9.9.9"


def test_strips_whitespace_around_last_entry():
    req = _request({"x-forwarded-for": "1.2.3.4,  9.9.9.9  "})
    assert real_client_ip(req) == "9.9.9.9"


def test_single_entry_x_forwarded_for():
    req = _request({"x-forwarded-for": "9.9.9.9"})
    assert real_client_ip(req) == "9.9.9.9"


def test_falls_back_to_client_host_without_header():
    req = _request({}, client_host="172.18.0.2")
    assert real_client_ip(req) == "172.18.0.2"


def test_falls_back_to_empty_string_without_client_or_header():
    req = _request({}, client_host=None)
    assert real_client_ip(req) == ""
