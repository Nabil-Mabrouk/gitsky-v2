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


def test_long_running_services_restart_unless_stopped():
    # Bug de prod réel (2026-09-20) : aucun service de ce fichier n'avait de
    # politique `restart` — contrairement au gabarit des projets générés, qui
    # pose `restart: unless-stopped` partout. `docker` (systemd) redémarre
    # bien tout seul après un reboot du VPS, mais sans cette politique,
    # Docker ne relance JAMAIS les conteneurs eux-mêmes : les projets
    # (cryptokilla, f-ynd...) sont remontés tout seuls après un reboot,
    # Traefik et le reste de shared_services sont restés morts — seul point
    # d'entrée HTTPS de toute la flotte, donc "le serveur est down" pour
    # tout le monde tant que quelqu'un ne relance pas `docker compose up -d`
    # à la main.
    services = _compose()["services"]
    for name in ("traefik", "postgres", "landing-collector", "llm-proxy", "umami"):
        assert services[name].get("restart") == "unless-stopped", name


def test_retired_geoip_services_are_gone():
    # Service geoip + one-shot geoipupdate retirés avec le module analytics
    # (2026-11-27) : la géolocalisation des visiteurs est faite par Umami.
    compose = _compose()
    assert "geoip" not in compose["services"]
    assert "geoipupdate" not in compose["services"]
    assert "geoip_data" not in (compose.get("volumes") or {})


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


def test_llm_net_is_internal_named_and_reserved_to_llm_proxy():
    # Réseau minimal pour les workers des projets (Chap 1/18, demande 0-hl
    # 2026-11-23) : ils n'y voient QUE llm-proxy — jamais postgres,
    # landing-collector. Nom explicite (pas de préfixe de projet
    # Compose) : les projets le rejoignent en external par ce nom.
    compose = _compose()
    net = compose["networks"]["llm-net"]
    assert net["internal"] is True
    assert net["name"] == "gitsky-llm-net"
    for name, service in compose["services"].items():
        nets = service.get("networks", [])
        if name == "llm-proxy":
            assert "llm-net" in nets
        else:
            assert "llm-net" not in nets, name


# --- Umami (Chap 13/18 §8, 2026-11-26) ---------------------------------------


def _umami() -> dict:
    return _compose()["services"]["umami"]


def test_umami_image_is_pinned_to_an_exact_version():
    # Jamais `latest` : un redéploiement de shared_services ne doit pas
    # monter de version (et migrer la base) par surprise. Tag vérifié sur
    # ghcr.io le 2026-11-26.
    assert _umami()["image"] == "ghcr.io/umami-software/umami:3.5.0"


def test_umami_uses_shared_postgres_and_required_secrets():
    env = list(_umami()["environment"])
    assert "DATABASE_URL=postgresql://umami:${UMAMI_DB_PASSWORD}@postgres:5432/umami" in env
    assert "APP_SECRET=${UMAMI_APP_SECRET}" in env
    assert "DISABLE_TELEMETRY=1" in env


def test_umami_tracker_and_collect_endpoint_are_renamed():
    # Les bloqueurs de pub filtrent script.js / /api/send d'Umami.
    env = list(_umami()["environment"])
    assert "TRACKER_SCRIPT_NAME=s.js" in env
    assert "COLLECT_API_ENDPOINT=/api/c" in env


def test_umami_is_exposed_only_on_its_stats_host():
    umami = _umami()
    assert set(umami["networks"]) == {"shared-services-net", "proxy-net"}
    labels = umami["labels"]
    rule = next(l for l in labels if ".rule=" in l)
    assert rule.endswith("=Host(`${UMAMI_HOST}`)")
    assert any("loadbalancer.server.port=3000" in l for l in labels)
    assert any("tls.certresolver=letsencrypt" in l for l in labels)
    assert umami.get("restart") == "unless-stopped"
    assert "ports" not in umami


def test_env_example_declares_umami_settings_empty():
    lines = (COMPOSE.parent / ".env.example").read_text(encoding="utf-8").splitlines()
    for key in ("UMAMI_HOST=", "UMAMI_DB_PASSWORD=", "UMAMI_APP_SECRET="):
        assert key in lines, key
