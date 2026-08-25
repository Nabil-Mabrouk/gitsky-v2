"""shared_services/docker-compose.yml (Chap 18) — routage Traefik du landing collector.

Deux bugs réels (constatés en prod, pas par un test) :

1. POST /leads sur le domaine d'une landing T0 (politique-ia) atterrissait
   sur le frontend statique du projet (serve -s, fallback SPA) au lieu du
   landing collector — aucune route Traefik n'existait jamais réellement
   vers lui, malgré le commentaire "same-origin, Traefik route" dans
   landing.html.jinja. Corrigé en joignant landing-collector à proxy-net
   avec un routeur SANS Host() (matche tous les domaines de la flotte) mais
   avec un Path() EXACT + Method(POST) — pour ne JAMAIS exposer
   /leads/{project} ni /leads/{project}/stats (protégés par
   COLLECTOR_STATS_TOKEN) au-delà de shared-services-net.
2. Une fois le double opt-in ajouté, le lien de confirmation
   (/leads/verify/{token}) redirigeait ENCORE vers la vitrine du projet
   plutôt que vers le landing collector — sans priority explicite, Traefik
   départage par défaut sur la longueur de la chaîne de règle, et le
   routeur frontend (Host(`<domaine>`)) s'est révélé plus long que
   PathPrefix(`/leads/verify`). Corrigé avec priority=100 explicite sur les
   deux routeurs du landing collector.
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
    rule = next(lab for lab in labels if "landing-collector-leads.rule=" in lab)
    # Path() exact (pas PathPrefix()) : /leads/{project} et
    # /leads/{project}/stats ne doivent JAMAIS matcher cette règle.
    assert "Path(`/leads`)" in rule
    assert "PathPrefix" not in rule
    assert "Method(`POST`)" in rule
    # Rule sans Host() : doit s'appliquer à tous les domaines de la flotte,
    # pas seulement à un domaine dédié au collecteur.
    assert "Host(" not in rule


def test_landing_collector_verify_router_reuses_leads_service():
    labels = _compose()["services"]["landing-collector"]["labels"]
    rule = next(lab for lab in labels if "landing-collector-verify.rule=" in lab)
    assert "PathPrefix(`/leads/verify`)" in rule
    assert "Host(" not in rule
    service_ref = next(
        lab for lab in labels if "landing-collector-verify.service=" in lab
    )
    assert service_ref.endswith("=landing-collector-leads")


def test_landing_collector_leads_router_is_rate_limited():
    labels = _compose()["services"]["landing-collector"]["labels"]
    assert any("leadslimit.ratelimit.average=" in lab for lab in labels)
    middlewares = next(
        lab for lab in labels if "landing-collector-leads.middlewares=" in lab
    )
    assert "leadslimit" in middlewares


def test_postgres_has_no_traefik_exposure():
    postgres = _compose()["services"]["postgres"]
    assert "proxy-net" not in postgres.get("networks", [])
    assert "labels" not in postgres


def test_leads_routers_have_explicit_priority():
    # Bug réel (constaté en prod) : sans priority explicite, Traefik
    # départage par défaut sur la LONGUEUR de la chaîne de règle — le
    # routeur frontend d'un projet (Host(`<domaine>`), pas de Host() ici)
    # s'est révélé plus long que PathPrefix(`/leads/verify`) et gagnait le
    # match, renvoyant le lien de confirmation vers la vitrine au lieu du
    # landing collector. Même valeur (100) que authlimit-{{ project_name }}
    # dans docker-compose.yml.jinja.
    labels = _compose()["services"]["landing-collector"]["labels"]
    assert "traefik.http.routers.landing-collector-leads.priority=100" in labels
    assert "traefik.http.routers.landing-collector-verify.priority=100" in labels
