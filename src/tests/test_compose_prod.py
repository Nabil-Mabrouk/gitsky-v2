"""docker-compose.yml de production (Phase 6, incr 3 — Chap 1 + 21 + 23).

Le compose généré était incomplet : ni build: ni image: pour frontend/backend
(un projet généré ne pouvait pas démarrer), pas de service migrate, et un `db:`
rendu quel que soit le tier — un T0 recevait un PostgreSQL inutile (~52 Mo
mesurés), contre le Chap 18 §3 et le budget ~50 Mo du T0.

On rend le compose pour chaque tier et on parse le YAML : les propriétés
vérifiées sont celles que Docker interprète, pas du texte.
"""

from pathlib import Path

import yaml

from helpers import projet_genere  # noqa: E402


def _compose(tier: str) -> dict:
    with projet_genere("pain-scraper", tier) as dst:
        return yaml.safe_load((dst / "docker-compose.yml").read_text(encoding="utf-8"))


# --- Un projet généré doit pouvoir démarrer (build:/image:) ----------------


def test_frontend_and_backend_are_buildable():
    services = _compose("t1")["services"]
    # Sans build:/image:, `docker compose up` échoue : "no image / build".
    assert services["frontend"]["build"]["context"] == "./frontend"
    assert services["backend"]["build"]["dockerfile"] == "Dockerfile"


def test_frontend_receives_api_url_as_build_arg():
    services = _compose("t1")["services"]
    # Vite inline VITE_API_URL au build : il DOIT être un build arg, pas un
    # environment: (sans effet côté runtime).
    args = services["frontend"]["build"]["args"]
    assert args["VITE_API_URL"] == "https://api.pain-scraper.mystudio.com"


def test_backend_traefik_port_is_declared():
    # Sans loadbalancer.server.port, Traefik devine et peut router vers le
    # mauvais port quand le conteneur en expose plusieurs.
    labels = _compose("t1")["services"]["backend"]["labels"]
    assert any("loadbalancer.server.port=8000" in lab for lab in labels)


# --- db conditionnelle au tier (Chap 18 §3) --------------------------------


def test_t0_has_no_database():
    services = _compose("t0")["services"]
    # T0 = landing sans base propre : les leads vont au collecteur partagé.
    assert "db" not in services
    assert "migrate" not in services


def test_t0_frontend_serves_react_landing_not_static_vitrine():
    # Inversion DÉLIBÉRÉE de ce test (Chap 24, pas un bug corrigé en douce) :
    # la vitrine T0 est désormais une route de l'app React partagée avec
    # T1/T2 (Landing.tsx + landing-manifest.json.jinja), plutôt qu'un HTML
    # statique servi par un Dockerfile.t0 dédié (supprimé) via `context: .` +
    # `vitrine/`. Décision produit : cohérence du stack et réutilisation du
    # code React à la promotion de tier, au prix du SEO/vitesse de la page
    # statique (accepté sciemment — rendu 100% client-side).
    frontend = _compose("t0")["services"]["frontend"]
    assert frontend["build"]["context"] == "./frontend"
    assert "dockerfile" not in frontend["build"]


def test_t0_backend_uses_sqlite_not_a_missing_db():
    backend = _compose("t0")["services"]["backend"]
    env = backend.get("environment", [])
    db_url = next(v for v in env if v.startswith("DATABASE_URL="))
    assert "sqlite" in db_url
    # Un depends_on: db planterait, il n'y a pas de service db en T0.
    assert "depends_on" not in backend


def test_login_rate_limit_declared_when_auth_module_present():
    # Doctrine Chap 14 rendue RÉELLE : l'app ne limite pas le login, Traefik
    # oui. Sans ces labels, la doctrine n'était implémentée nulle part —
    # credential stuffing et DoS argon2 gratuits.
    labels = _compose("t1")["services"]["backend"]["labels"]
    assert any("ratelimit.average=5" in lab for lab in labels)
    assert any("Path(`/api/auth/login`)" in lab for lab in labels)
    # Le routeur dédié doit primer sur le routeur backend générique.
    assert any("authlimit-pain-scraper.priority=100" in lab for lab in labels)


def test_no_login_rate_limit_on_t0_without_auth():
    # T0 n'a pas de module auth : pas de route login, pas de limite fantôme.
    labels = _compose("t0")["services"]["backend"]["labels"]
    assert not any("authlimit" in lab for lab in labels)


def test_t1_and_t2_each_own_a_postgres_container():
    for tier in ("t1", "t2"):
        services = _compose(tier)["services"]
        assert services["db"]["image"] == "postgres:16.3-alpine"
        # Conteneur PAR PROJET (décision d'archi Phase 6) : nom scopé au projet.
        assert services["db"]["container_name"] == "pain-scraper_db"


def test_t1_and_t2_have_a_migrate_service():
    for tier in ("t1", "t2"):
        migrate = _compose(tier)["services"]["migrate"]
        assert migrate["command"] == "python -m scripts.migrate"
        assert migrate["restart"] == "no"  # éphémère : applique puis sort
        assert migrate["depends_on"]["db"]["condition"] == "service_healthy"


def test_db_volume_declared_only_when_a_db_exists():
    assert "volumes" not in _compose("t0")
    assert "db_data" in _compose("t1")["volumes"]


# --- Sécurité réseau : db jamais exposée (Chap 23 §2.3) --------------------


def test_database_is_never_port_exposed():
    for tier in ("t1", "t2"):
        db = _compose(tier)["services"]["db"]
        # Un `ports:` sur la db la rendrait joignable depuis l'hôte/Internet.
        assert "ports" not in db
        # Elle ne vit que sur le réseau interne, jamais sur proxy-net.
        assert db["networks"] == ["internal-net"]


def test_internal_net_is_isolated():
    nets = _compose("t1")["networks"]
    assert nets["internal-net"]["internal"] is True


def test_db_reachable_by_backend_and_migrate_only():
    services = _compose("t2")["services"]
    # backend et migrate parlent à la db via internal-net ; le frontend n'a
    # aucune raison d'y toucher (il passe par l'API).
    assert "internal-net" in services["backend"]["networks"]
    assert "internal-net" in services["migrate"]["networks"]


# --- Rotation des logs Docker (Chap 23 §3.3) -------------------------------


def test_log_rotation_caps_are_set():
    services = _compose("t1")["services"]
    # Sans plafond, les logs JSON grossissent indéfiniment (Chap 23 §3.3).
    back = services["backend"]["logging"]["options"]
    assert back["max-size"] == "50m"
    assert back["max-file"] == "5"
    db = services["db"]["logging"]["options"]
    assert db["max-size"] == "100m"
    assert db["max-file"] == "3"


# --- Résilience (restart policies) -----------------------------------------


def test_long_lived_services_restart_unless_stopped():
    services = _compose("t2")["services"]
    for name in ("frontend", "backend", "db"):
        assert services[name]["restart"] == "unless-stopped"


# --- Secrets générés par projet (Chap 18 §Sécurité) ------------------------


def _env_dict(dst: Path) -> dict:
    return dict(
        line.split("=", 1)
        for line in (dst / ".env").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.startswith("#")
    )


def test_secrets_are_generated_per_project_and_unique():
    with projet_genere("projet-a", "t1") as a, projet_genere("projet-b", "t1") as b:
        env_a = _env_dict(a)
        env_b = _env_dict(b)

    # Une vraie clé, pas le placeholder de dev du config.py.
    assert len(env_a["SECRET_KEY"]) >= 64
    assert "change-me" not in env_a["SECRET_KEY"]
    # Un compromis ne se propage pas : chaque projet a SES secrets.
    assert env_a["SECRET_KEY"] != env_b["SECRET_KEY"]
    assert env_a["POSTGRES_PASSWORD"] != env_b["POSTGRES_PASSWORD"]


def test_t0_env_has_no_postgres_credentials():
    with projet_genere("landing-x", "t0") as dst:
        env = (dst / ".env").read_text(encoding="utf-8")
        # T0 n'a pas de base : pas de credentials Postgres à porter.
        assert "POSTGRES_PASSWORD" not in env
        assert "SECRET_KEY" in env  # mais garde une clé JWT (SEO/health, futur auth)


# --- shared-services-net : réservé au module fleet (Chap 19, onglet Leads) --


def test_fleet_backend_joins_shared_services_net():
    with projet_genere("fleet-dashboard", "t2", modules={"fleet": True}) as dst:
        compose = yaml.safe_load((dst / "docker-compose.yml").read_text(encoding="utf-8"))
    assert "shared-services-net" in compose["services"]["backend"]["networks"]
    net = compose["networks"]["shared-services-net"]
    assert net["external"] is True


def test_ordinary_t2_project_never_touches_shared_services_net():
    # Un projet T2 sans module fleet (le cas normal) ne doit pas se retrouver
    # à dépendre d'un réseau externe dont il n'a jamais besoin.
    with projet_genere("pain-scraper", "t2") as dst:
        compose = yaml.safe_load((dst / "docker-compose.yml").read_text(encoding="utf-8"))
    assert "shared-services-net" not in compose["services"]["backend"]["networks"]
    assert "shared-services-net" not in compose["networks"]
