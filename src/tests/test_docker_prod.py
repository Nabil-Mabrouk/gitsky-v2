"""Dockerfile de production du backend (Phase 6, incr 1 — Chap 21).

Le Dockerfile est un artefact GÉNÉRÉ : on le rend via Copier et on vérifie les
propriétés que le Chap 21 exige — multi-stage, non-root, healthcheck, un seul
artefact quels que soient les modules activés (ils se décident au runtime via
le .env, jamais au build).

La validation « l'image build et répond vraiment » est l'incrément 8 (nécessite
un démon Docker) ; ici on valide la structure, ce qui est testable sans Docker.
"""

import re
from pathlib import Path

from helpers import projet_genere  # noqa: E402

SRC = Path(__file__).resolve().parents[1]
GENERATOR = SRC / "generator"


def _render(**data) -> str:
    # skip_tasks : ces tests ne LISENT que des fichiers, pas besoin du commit
    # initial (et on évite la flakiness Windows du git add).
    with projet_genere("pain-scraper", **data) as dst:
        return (dst / "Dockerfile").read_text(encoding="utf-8")


def _directives(body: str) -> str:
    """Le Dockerfile sans ses commentaires.

    Les tests « rien ne fuite dans l'image » doivent porter sur ce que Docker
    exécute, pas sur la prose : les commentaires citent légitimement le .env et
    la classe dépréciée du livre.
    """
    return "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )


def _env(**data) -> set[str]:
    with projet_genere("pain-scraper", **data) as dst:
        return set((dst / ".env").read_text(encoding="utf-8").splitlines())


# --- Multi-stage (Chap 21 §« Le Pattern Multi-Stage ») --------------------


def test_dockerfile_is_multi_stage():
    body = _render()
    stages = re.findall(r"^FROM\s+(\S+)\s+AS\s+(\S+)", body, re.MULTILINE)
    assert [name for _, name in stages] == ["builder", "production"]
    # L'intérêt du multi-stage : le résultat du builder est recopié, les outils
    # de build restent derrière. Sans ce COPY --from, les deux stages seraient
    # décoratifs.
    assert "COPY --from=builder" in body


def test_builder_installs_user_local_and_production_copies_it():
    body = _render()
    assert "pip install --no-cache-dir --user -r requirements.txt" in body
    assert "/root/.local /home/appuser/.local" in body
    # pip ne doit pas être réinstallé côté production.
    production = body.split("AS production", 1)[1]
    assert "pip install" not in production


# --- Sécurité : jamais root (Chap 21 §« Sécurité des Conteneurs ») ---------


def test_container_does_not_run_as_root():
    body = _render()
    assert "RUN groupadd -r appuser && useradd -r -g appuser appuser" in body
    # Le dernier USER déclaré est celui qui exécute le CMD : c'est lui qui
    # compte, pas la simple présence d'une ligne USER quelque part.
    users = re.findall(r"^USER\s+(\S+)", body, re.MULTILINE)
    assert users[-1] == "appuser"


def test_application_code_is_owned_by_appuser():
    body = _render()
    # appuser exécute le code mais ne doit pas pouvoir le réécrire.
    assert "COPY --chown=appuser:appuser . ." in body


# --- Healthcheck (Chap 21 §« Surveillance de l'État ») ---------------------


def test_healthcheck_polls_health_every_30s():
    body = _render()
    assert "HEALTHCHECK" in body
    assert "--interval=30s" in body  # cadence explicite du livre
    assert "/health" in body


def test_healthcheck_uses_python_not_an_extra_package():
    # On sonde avec Python (déjà présent) plutôt que curl : pas de couche apt,
    # image plus légère, build sans dépendance réseau supplémentaire.
    body = _render()
    assert "urllib.request" in body
    assert "apt-get" not in _directives(body)


def test_appuser_has_a_writable_data_dir_while_code_stays_readonly():
    # Bug attrapé par le build réel : /app est root (code en RO, règle Chap 21).
    # /data est le seul emplacement inscriptible par appuser.
    body = _render()
    assert "mkdir -p /data && chown appuser:appuser /data" in body
    # Le code n'est jamais chown pour appuser en écriture : /app reste root.
    assert "chown appuser:appuser /app" not in body


# --- Workers Gunicorn (Chap 21 §« Gunicorn + Uvicorn ») --------------------


def test_default_worker_count_is_two():
    # WEB_CONCURRENCY est lu nativement par Gunicorn (gunicorn.config.Workers).
    # Simple valeur de configuration par projet (Chap 21), plus dérivée d'un
    # palier — 2 est le défaut raisonnable pour un premier déploiement.
    assert "WEB_CONCURRENCY=2" in _env()


def test_worker_count_is_configurable_per_project():
    env = _env(project={"name": "pain-scraper", "workers": 5})
    assert "WEB_CONCURRENCY=5" in env


def test_worker_count_is_not_baked_into_the_image():
    # Le cœur de la promesse « ajuster sans rebuild » : un -w figé dans le CMD
    # imposerait de rebuilder l'image pour changer le nombre de workers.
    assert '"-w"' not in _directives(_render())


def test_gunicorn_serves_the_app_with_uvicorn_workers():
    directives = _directives(_render())
    assert '"gunicorn", "app.core.main:app"' in directives
    assert '"--bind", "0.0.0.0:8000"' in directives
    # uvicorn.workers est déprécié depuis uvicorn 0.30 : on veut le paquet
    # uvicorn-worker, pas la classe du livre.
    assert "uvicorn_worker.UvicornWorker" in directives
    assert "uvicorn.workers.UvicornWorker" not in directives


def test_worker_class_is_installable():
    # Régression : un -k pointant une classe absente de requirements.txt ne
    # casse qu'au démarrage du conteneur, pas au build.
    requirements = (
        GENERATOR / "template" / "requirements.txt"
    ).read_text(encoding="utf-8")
    assert "gunicorn" in requirements
    assert "uvicorn-worker" in requirements


# --- Un seul artefact, quels que soient les modules (Chap 21) --------------


def test_single_artifact_is_byte_identical_across_module_combinations():
    # La promesse du livre : une seule image à builder, à stocker, à auditer.
    # Les modules ne se décident pas au build — les rendus sont identiques au
    # byte près, commentaires compris, qu'aucun ou tous les modules soient actifs.
    assert _render() == _render(modules={"admin": True, "agentic": True, "fleet": True})


def test_no_module_flag_leaks_into_the_image():
    # Les modules se décident à l'exécution via le .env, jamais au build : un
    # MODULE_* figé casserait tout changement de configuration sans rebuild.
    directives = _directives(_render(modules={"agentic": True}))
    assert "MODULE_" not in directives
    assert "GITSKY_TIER" not in directives


# --- Contexte de build (.dockerignore) -------------------------------------


def test_dockerignore_keeps_secrets_and_frontend_out_of_the_image():
    with projet_genere("pain-scraper") as dst:
        ignored = set(
            line.strip()
            for line in (dst / ".dockerignore").read_text(encoding="utf-8").splitlines()
        )
        # Le COPY . . du Dockerfile embarquerait sinon tout le contexte.
        assert {".env", ".git", "frontend", "node_modules"} <= ignored
