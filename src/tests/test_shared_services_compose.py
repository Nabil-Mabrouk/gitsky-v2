"""shared_services/docker-compose.yml (Chap 18) — routage Traefik du landing collector.

Bug réel (constaté en prod, pas par un test) : POST /leads sur le domaine
d'une landing T0 (politique-ia) atterrissait sur le frontend statique du
projet (serve -s, fallback SPA) au lieu du landing collector — aucune route
Traefik n'existait jamais réellement vers lui, malgré le commentaire
"same-origin, Traefik route" dans landing.html.jinja. Corrigé en joignant
landing-collector à proxy-net avec un routeur SANS Host() (matche tous les
domaines de la flotte) mais avec un Path() EXACT + Method(POST) — pour ne
JAMAIS exposer /leads/{project} ni /leads/{project}/stats (protégés par
COLLECTOR_STATS_TOKEN) au-delà de shared-services-net.
"""

from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parents[1] / "shared_services" / "docker-compose.yml"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_landing_collector_joins_both_networks():
    services = _compose()["services"]
    nets = services["landing-collector"]["networks"]
    assert "shared-services-net" in nets
    assert "proxy-net" in nets


def test_landing_collector_traefik_rule_is_exact_path_not_prefix():
    labels = _compose()["services"]["landing-collector"]["labels"]
    rule = next(lab for lab in labels if ".rule=" in lab)
    # Path() exact (pas PathPrefix()) : /leads/{project} et
    # /leads/{project}/stats ne doivent JAMAIS matcher cette règle.
    assert "Path(`/leads`)" in rule
    assert "PathPrefix" not in rule
    assert "Method(`POST`)" in rule
    # Rule sans Host() : doit s'appliquer à tous les domaines de la flotte,
    # pas seulement à un domaine dédié au collecteur.
    assert "Host(" not in rule


def test_postgres_has_no_traefik_exposure():
    postgres = _compose()["services"]["postgres"]
    assert "proxy-net" not in postgres.get("networks", [])
    assert "labels" not in postgres
