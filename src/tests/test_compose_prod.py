"""docker-compose.yml de production (Phase 6, incr 3 — Chap 1 + 21 + 23).

Le compose généré était incomplet : ni build: ni image: pour frontend/backend
(un projet généré ne pouvait pas démarrer), pas de service migrate. Depuis la
suppression des tiers (Chap 2), chaque projet reçoit systématiquement sa base
PostgreSQL — plus de branche conditionnelle à vérifier, un seul rendu de
référence suffit pour la majorité des tests.

On rend le compose et on parse le YAML : les propriétés vérifiées sont celles
que Docker interprète, pas du texte.
"""

from pathlib import Path

import yaml

from helpers import projet_genere  # noqa: E402


def _compose() -> dict:
    with projet_genere("pain-scraper") as dst:
        return yaml.safe_load((dst / "docker-compose.yml").read_text(encoding="utf-8"))


# --- Un projet généré doit pouvoir démarrer (build:/image:) ----------------


def test_frontend_and_backend_are_buildable():
    services = _compose()["services"]
    # Sans build:/image:, `docker compose up` échoue : "no image / build".
    assert services["frontend"]["build"]["context"] == "./frontend"
    assert services["backend"]["build"]["dockerfile"] == "Dockerfile"


def test_frontend_receives_api_url_as_build_arg():
    services = _compose()["services"]
    # Vite inline VITE_API_URL au build : il DOIT être un build arg, pas un
    # environment: (sans effet côté runtime).
    args = services["frontend"]["build"]["args"]
    assert args["VITE_API_URL"] == "https://api.pain-scraper.mystudio.com"


def test_backend_traefik_port_is_declared():
    # Sans loadbalancer.server.port, Traefik devine et peut router vers le
    # mauvais port quand le conteneur en expose plusieurs.
    labels = _compose()["services"]["backend"]["labels"]
    assert any("loadbalancer.server.port=8000" in lab for lab in labels)


# --- db inconditionnelle, un conteneur PAR PROJET (Chap 18 §2) -------------


def test_every_project_owns_a_postgres_container():
    services = _compose()["services"]
    assert services["db"]["image"] == "postgres:16.3-alpine"
    # Conteneur PAR PROJET (décision d'archi Phase 6) : nom scopé au projet.
    assert services["db"]["container_name"] == "pain-scraper_db"


def test_backend_uses_postgres_and_depends_on_it():
    backend = _compose()["services"]["backend"]
    env = backend.get("environment", [])
    db_url = next(v for v in env if v.startswith("DATABASE_URL="))
    assert "postgresql+asyncpg" in db_url
    assert backend["depends_on"]["db"]["condition"] == "service_healthy"


def test_frontend_serves_react_landing():
    # La landing est une route de l'app React (Landing.tsx +
    # landing-manifest.json.jinja), jamais un HTML statique servi par un
    # Dockerfile dédié — cohérence du stack, quels que soient les modules.
    frontend = _compose()["services"]["frontend"]
    assert frontend["build"]["context"] == "./frontend"
    assert "dockerfile" not in frontend["build"]


def test_login_rate_limit_always_declared():
    # Doctrine Chap 14 rendue RÉELLE : l'app ne limite pas le login, Traefik
    # oui. L'auth est core (Chap 2 §1) : ces labels sont donc inconditionnels.
    labels = _compose()["services"]["backend"]["labels"]
    assert any("ratelimit.average=5" in lab for lab in labels)
    assert any("Path(`/api/auth/login`)" in lab for lab in labels)
    # Le routeur dédié doit primer sur le routeur backend générique.
    assert any("authlimit-pain-scraper.priority=100" in lab for lab in labels)


def test_has_a_migrate_service():
    migrate = _compose()["services"]["migrate"]
    assert migrate["command"] == "python -m scripts.migrate"
    assert migrate["restart"] == "no"  # éphémère : applique puis sort
    assert migrate["depends_on"]["db"]["condition"] == "service_healthy"


def test_db_volume_always_declared():
    assert "db_data" in _compose()["volumes"]


# --- Sécurité réseau : db jamais exposée (Chap 23 §2.3) --------------------


def test_database_is_never_port_exposed():
    db = _compose()["services"]["db"]
    # Un `ports:` sur la db la rendrait joignable depuis l'hôte/Internet.
    assert "ports" not in db
    # Elle ne vit que sur le réseau interne, jamais sur proxy-net.
    assert db["networks"] == ["internal-net"]


def test_internal_net_is_isolated():
    nets = _compose()["networks"]
    assert nets["internal-net"]["internal"] is True


def test_db_reachable_by_backend_and_migrate_only():
    services = _compose()["services"]
    # backend et migrate parlent à la db via internal-net ; le frontend n'a
    # aucune raison d'y toucher (il passe par l'API).
    assert "internal-net" in services["backend"]["networks"]
    assert "internal-net" in services["migrate"]["networks"]


# --- Rotation des logs Docker (Chap 23 §3.3) -------------------------------


def test_log_rotation_caps_are_set():
    services = _compose()["services"]
    # Sans plafond, les logs JSON grossissent indéfiniment (Chap 23 §3.3).
    back = services["backend"]["logging"]["options"]
    assert back["max-size"] == "50m"
    assert back["max-file"] == "5"
    db = services["db"]["logging"]["options"]
    assert db["max-size"] == "100m"
    assert db["max-file"] == "3"


# --- Résilience (restart policies) -----------------------------------------


def test_long_lived_services_restart_unless_stopped():
    services = _compose()["services"]
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
    with projet_genere("projet-a") as a, projet_genere("projet-b") as b:
        env_a = _env_dict(a)
        env_b = _env_dict(b)

    # Une vraie clé, pas le placeholder de dev du config.py.
    assert len(env_a["SECRET_KEY"]) >= 64
    assert "change-me" not in env_a["SECRET_KEY"]
    # Un compromis ne se propage pas : chaque projet a SES secrets.
    assert env_a["SECRET_KEY"] != env_b["SECRET_KEY"]
    assert env_a["POSTGRES_PASSWORD"] != env_b["POSTGRES_PASSWORD"]


def test_env_has_postgres_credentials_and_secret_key():
    with projet_genere("landing-x") as dst:
        env = (dst / ".env").read_text(encoding="utf-8")
        assert "POSTGRES_PASSWORD" in env
        assert "SECRET_KEY" in env


# --- shared-services-net : réservé au module fleet (Chap 19, onglet Leads) --


def test_fleet_backend_joins_shared_services_net():
    with projet_genere("fleet-dashboard", modules={"fleet": True}) as dst:
        compose = yaml.safe_load((dst / "docker-compose.yml").read_text(encoding="utf-8"))
    assert "shared-services-net" in compose["services"]["backend"]["networks"]
    net = compose["networks"]["shared-services-net"]
    assert net["external"] is True


def test_ordinary_project_never_touches_shared_services_net():
    # Un projet sans module fleet ni leads (le cas normal) ne doit pas se
    # retrouver à dépendre d'un réseau externe dont il n'a jamais besoin.
    with projet_genere("pain-scraper") as dst:
        compose = yaml.safe_load((dst / "docker-compose.yml").read_text(encoding="utf-8"))
    assert "shared-services-net" not in compose["services"]["backend"]["networks"]
    assert "shared-services-net" not in compose["networks"]


def test_leads_backend_joins_shared_services_net():
    # module_leads a besoin du meme reseau interne que fleet pour joindre
    # landing_collector (GET /leads/{project} n'est jamais expose via
    # Traefik, round leads) — sans monter les volumes fleet-only.
    with projet_genere("pain-scraper", modules={"leads": True}) as dst:
        compose = yaml.safe_load((dst / "docker-compose.yml").read_text(encoding="utf-8"))
    assert "shared-services-net" in compose["services"]["backend"]["networks"]
    net = compose["networks"]["shared-services-net"]
    assert net["external"] is True
    assert "volumes" not in compose["services"]["backend"]


# --- volumes du générateur : réservés au module fleet (Chap 27) ------------


def test_fleet_backend_mounts_generator_and_projects_dir():
    # Sans ces montages, `copier.run_copy` (Chap 27) n'a aucun accès
    # filesystem réel aux chemins hôte désignés par GITSKY_GENERATOR_PATH /
    # PROJECTS_DIR, quelle que soit leur valeur dans .env.
    with projet_genere("fleet-dashboard", modules={"fleet": True}) as dst:
        compose = yaml.safe_load((dst / "docker-compose.yml").read_text(encoding="utf-8"))
    volumes = compose["services"]["backend"]["volumes"]
    assert any(v.startswith("${GITSKY_GENERATOR_PATH") and v.endswith(":ro") for v in volumes)
    assert any(
        v.startswith("${PROJECTS_DIR") and not v.endswith(":ro") for v in volumes
    )


def test_fleet_backend_mounts_monorepo_gitdir():
    # Bug de prod réel : src/generator est un sous-module git, son .git n'est
    # qu'un pointeur ("gitdir: ../../.git/modules/src/generator") vers le
    # vrai dépôt dans le .git du monorepo parent. Sans CE montage en plus de
    # GITSKY_GENERATOR_PATH, `copier.run_copy` exécuté dans ce conteneur ne
    # peut jamais résoudre le commit du template — aucune erreur visible,
    # juste `_commit` absent de .copier-answers.yml, et donc un projet créé
    # via le wizard qui ne peut plus jamais recevoir `copier update`.
    with projet_genere("fleet-dashboard", modules={"fleet": True}) as dst:
        compose = yaml.safe_load((dst / "docker-compose.yml").read_text(encoding="utf-8"))
    volumes = compose["services"]["backend"]["volumes"]
    assert any(v.startswith("${GITSKY_MONOREPO_GITDIR") and v.endswith(":ro") for v in volumes)


def test_ordinary_project_has_no_backend_volumes():
    # Un projet sans module fleet n'a aucune raison de monter quoi que ce
    # soit d'hôte dans son backend.
    with projet_genere("pain-scraper") as dst:
        compose = yaml.safe_load((dst / "docker-compose.yml").read_text(encoding="utf-8"))
    assert "volumes" not in compose["services"]["backend"]


# --- docker-compose.maintenance.yml (Chap 20/23, round sécurisation) -------


def test_maintenance_compose_ships_for_every_project_not_just_fleet():
    # Le mode maintenance est un besoin générique (n'importe quel projet peut
    # y passer), contrairement aux montages fleet ci-dessus — généré pour
    # tout projet, pas seulement module_fleet.
    with projet_genere("pain-scraper") as dst:
        assert (dst / "docker-compose.maintenance.yml").is_file()
        assert (dst / "maintenance" / "index.html").is_file()


def test_maintenance_service_claims_the_same_traefik_routes_as_the_real_app():
    # C'est le point critique : la page de maintenance doit prendre le relais
    # sur EXACTEMENT les mêmes domaines que le frontend/backend réels
    # (Host() du docker-compose.yml principal), sinon lifecycle-fleet.sh
    # bascule en maintenance sans que Traefik ne route jamais vers elle.
    with projet_genere("pain-scraper") as dst:
        main_compose = yaml.safe_load((dst / "docker-compose.yml").read_text(encoding="utf-8"))
        maint_compose = yaml.safe_load(
            (dst / "docker-compose.maintenance.yml").read_text(encoding="utf-8")
        )

    def _host_rules(labels: list[str]) -> set[str]:
        return {l.split("=", 1)[1] for l in labels if ".rule=" in l and "Host(" in l}

    frontend_rules = _host_rules(main_compose["services"]["frontend"]["labels"])
    backend_rules = _host_rules(main_compose["services"]["backend"]["labels"])
    maint_labels = maint_compose["services"]["maintenance"]["labels"]
    maint_rules = _host_rules(maint_labels)

    # Domaine par défaut sans surcharge (Chap 1) : {nom}.mystudio.com.
    assert any("Host(`pain-scraper.mystudio.com`)" in r for r in frontend_rules)
    assert any("Host(`api.pain-scraper.mystudio.com`)" in r for r in backend_rules)
    assert any("Host(`pain-scraper.mystudio.com`)" in r for r in maint_rules)
    assert any("Host(`api.pain-scraper.mystudio.com`)" in r for r in maint_rules)


def test_maintenance_service_uses_the_shared_proxy_net_not_internal_net():
    # La page de maintenance n'a besoin d'aucun accès à la base/au réseau
    # interne (Chap 23 §2.3) — seulement d'être visible de Traefik.
    with projet_genere("pain-scraper") as dst:
        maint_compose = yaml.safe_load(
            (dst / "docker-compose.maintenance.yml").read_text(encoding="utf-8")
        )
    assert maint_compose["services"]["maintenance"]["networks"] == ["proxy-net"]


# --- service worker : réservé au module worker (round worker) --------------


def test_worker_service_appears_when_module_active():
    with projet_genere("pain-scraper", modules={"worker": True}) as dst:
        compose = yaml.safe_load((dst / "docker-compose.yml").read_text(encoding="utf-8"))
    worker = compose["services"]["worker"]
    assert worker["command"] == "python -m app.modules.worker.runner"
    assert worker["restart"] == "unless-stopped"
    assert worker["container_name"] == "pain-scraper_worker"
    assert worker["depends_on"]["db"]["condition"] == "service_healthy"


def test_worker_service_absent_by_default():
    # Un projet sans module worker (le cas normal) ne doit avoir aucune trace
    # d'un service qui ne lui sert à rien.
    with projet_genere("pain-scraper") as dst:
        compose = yaml.safe_load((dst / "docker-compose.yml").read_text(encoding="utf-8"))
    assert "worker" not in compose["services"]


def test_worker_healthcheck_is_disabled():
    # Le Dockerfile sonde localhost:8000/health (process gunicorn) — worker
    # ne sert aucun port HTTP, cette sonde échouerait toujours sans ce
    # disable (piège trouvé en concevant ce module).
    with projet_genere("pain-scraper", modules={"worker": True}) as dst:
        compose = yaml.safe_load((dst / "docker-compose.yml").read_text(encoding="utf-8"))
    assert compose["services"]["worker"]["healthcheck"]["disable"] is True


def test_worker_stop_grace_period_gives_cycles_time_to_exit():
    # Défaut Docker (10s, jamais overridé ailleurs dans ce fichier) trop
    # court pour un cycle avec I/O externe (exchange, LLM du bulletin).
    with projet_genere("pain-scraper", modules={"worker": True}) as dst:
        compose = yaml.safe_load((dst / "docker-compose.yml").read_text(encoding="utf-8"))
    assert compose["services"]["worker"]["stop_grace_period"] == "90s"


def test_worker_never_joins_proxy_net():
    # Pas HTTP-facing, aucune raison d'être exposé à Traefik.
    with projet_genere("pain-scraper", modules={"worker": True}) as dst:
        compose = yaml.safe_load((dst / "docker-compose.yml").read_text(encoding="utf-8"))
    networks = compose["services"]["worker"]["networks"]
    assert "internal-net" in networks
    assert "proxy-net" not in networks
