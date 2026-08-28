"""`.env.local` prime sur `.env` (Chap 23, round sécurisation).

Contrairement à `.env`, `.env.local` n'est jamais un `.jinja` du template —
il ne peut donc structurellement jamais être écrasé par `copier update`. Ce
test prouve juste le comportement de chargement côté Settings ; la garantie
"jamais un .jinja" est structurelle (aucun fichier `.env.local.jinja`
n'existe dans le template) et vérifiée par grep dans test_generator_spike.py
(`.env.local` absent des fichiers suivis, `.env.local.example` présent).
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generator" / "template"))

from app.core.config import Settings  # noqa: E402
from helpers import projet_genere  # noqa: E402


def test_env_local_overrides_env_for_the_same_key():
    with tempfile.TemporaryDirectory() as tmp:
        env = Path(tmp) / ".env"
        env_local = Path(tmp) / ".env.local"
        env.write_text("SITE_URL=https://from-env.example\n", encoding="utf-8")
        env_local.write_text("SITE_URL=https://from-env-local.example\n", encoding="utf-8")

        s = Settings(_env_file=(str(env), str(env_local)))

        assert s.site_url == "https://from-env-local.example"


def test_env_local_alone_still_supplies_its_values():
    with tempfile.TemporaryDirectory() as tmp:
        env = Path(tmp) / ".env"
        env_local = Path(tmp) / ".env.local"
        env.write_text("PROJECT_NAME=demo\n", encoding="utf-8")
        env_local.write_text("FLEET_GITHUB_WEBHOOK_SECRET=abc123\n", encoding="utf-8")

        s = Settings(_env_file=(str(env), str(env_local)))

        assert s.project_name == "demo"
        assert s.fleet_github_webhook_secret == "abc123"


def test_env_local_example_lists_fleet_vars_only_when_module_fleet_active():
    with projet_genere("pain-scraper") as dst:
        example = (dst / ".env.local.example").read_text(encoding="utf-8")
    assert "FLEET_GITHUB_TOKEN=" not in example

    with projet_genere("fleet-dashboard", modules={"fleet": True}) as dst:
        example = (dst / ".env.local.example").read_text(encoding="utf-8")
    assert "FLEET_GITHUB_TOKEN=" in example
    assert "SMTP_PASSWORD=" in example
    # GITSKY_GENERATOR_PATH/GITSKY_MONOREPO_GITDIR/PROJECTS_DIR restent dans
    # .env : docker-compose.yml les lit en ${VAR:-défaut} pour ses montages,
    # et Compose ne lit QUE .env pour sa propre substitution, jamais
    # .env.local — les y mettre les rendrait invisibles à Compose (Chap 27).
    assert "GITSKY_GENERATOR_PATH=" not in example
    assert "GITSKY_MONOREPO_GITDIR=" not in example
    assert "PROJECTS_DIR=" not in example


def test_compose_backend_loads_env_local_as_optional():
    with projet_genere("fleet-dashboard", modules={"fleet": True}) as dst:
        compose = (dst / "docker-compose.yml").read_text(encoding="utf-8")
    assert "path: .env.local" in compose
    assert "required: false" in compose
