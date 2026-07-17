"""Dockerfile de production du frontend (Phase 6, incr 2 — Chap 21).

Le gain du multi-stage est ici maximal : le dernier stage ne doit contenir que
`dist` (quelques Mo de JS/CSS), ni node_modules ni toolchain Vite.

Comme le Dockerfile backend, ce fichier ne contient aucune variable Jinja : ce
qui varie par projet (l'URL de l'API) arrive par --build-arg. La validation
« l'image build et sert vraiment » est l'incrément 8 (nécessite Docker).
"""

import json
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
GENERATOR = SRC / "generator"
sys.path.insert(0, str(SRC / "tests"))

from helpers import projet_genere  # noqa: E402

TEMPLATE_FRONTEND = GENERATOR / "template" / "frontend"


def _render(tier: str = "t1") -> str:
    with projet_genere("pain-scraper", tier) as dst:
        return (dst / "frontend" / "Dockerfile").read_text(encoding="utf-8")


def _directives(body: str) -> str:
    return "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )


# --- Trois stages, dist seul en production (Chap 21 §« Frontend ») ---------


def test_frontend_is_three_stage():
    stages = re.findall(r"^FROM\s+(\S+)\s+AS\s+(\S+)", _render(), re.MULTILINE)
    assert [name for _, name in stages] == ["deps", "build", "production"]


def test_production_stage_ships_dist_only():
    production = _render().split("AS production", 1)[1]
    assert "COPY --from=build --chown=node:node /app/dist ./dist" in production
    # Tout l'intérêt du 3e stage : ni modules npm ni toolchain de build.
    assert "node_modules" not in _directives(production)
    assert "npm ci" not in production
    assert "npm run build" not in production


def test_build_stage_reuses_deps_modules():
    body = _render()
    assert "COPY --from=deps /app/node_modules ./node_modules" in body
    assert "npm run build" in body


# --- Reproductibilité du build (npm ci + lockfile) -------------------------


def test_build_is_reproducible_via_npm_ci():
    body = _render()
    # npm install résoudrait les ^ranges à chaque build : deux images depuis le
    # même commit pourraient embarquer des versions différentes.
    assert "RUN npm ci" in body
    assert "RUN npm install -r" not in body


def test_lockfile_ships_with_the_template():
    # npm ci ÉCHOUE sans lockfile : sans ce fichier le Dockerfile ne build pas.
    lock = TEMPLATE_FRONTEND / "package-lock.json"
    assert lock.is_file()
    data = json.loads(lock.read_text(encoding="utf-8"))
    assert data["lockfileVersion"] >= 3


def test_lockfile_is_generated_in_projects():
    with projet_genere("pain-scraper", "t1") as dst:
        assert (dst / "frontend" / "package-lock.json").is_file()


def test_lockfile_matches_package_json_dependencies():
    # Un lockfile qui a dérivé du package.json fait échouer `npm ci` (et non
    # retomber sur une résolution silencieuse).
    manifest = json.loads(
        (TEMPLATE_FRONTEND / "package.json").read_text(encoding="utf-8")
    )
    lock = json.loads(
        (TEMPLATE_FRONTEND / "package-lock.json").read_text(encoding="utf-8")
    )
    racine = lock["packages"][""]
    assert racine["dependencies"] == manifest["dependencies"]
    assert racine["devDependencies"] == manifest["devDependencies"]


# --- Sécurité : jamais root (Chap 21 §« Sécurité des Conteneurs ») ---------


def test_frontend_does_not_run_as_root():
    body = _render()
    users = re.findall(r"^USER\s+(\S+)", body, re.MULTILINE)
    assert users[-1] == "node"  # utilisateur non-root fourni par l'image node


# --- Base image supportée --------------------------------------------------


def test_base_image_is_a_supported_node_lts():
    # Node 20 est EOL depuis le 2026-04-30 : plus aucun correctif de sécurité.
    # Le Chap 23 le tire encore (update_images.sh) — écart assumé et consigné.
    bases = set(re.findall(r"^FROM\s+(\S+)", _render(), re.MULTILINE))
    assert bases == {"node:24-alpine"}


# --- URL d'API inlinée au build (spécificité Vite) -------------------------


def test_api_url_arrives_as_build_arg():
    body = _render()
    # Vite inline les VITE_* dans le bundle : une injection au runtime (compose
    # `environment:`) n'aurait aucun effet.
    assert "ARG VITE_API_URL" in body
    assert "ENV VITE_API_URL=$VITE_API_URL" in body


def test_build_fails_loudly_without_api_url():
    body = _render()
    # Sans garde, Vite inlinerait "" et livrerait un bundle qui n'appelle rien.
    assert 'test -n "$VITE_API_URL"' in body
    assert "exit 1" in body


def test_dev_api_url_cannot_leak_into_the_bundle():
    with projet_genere("pain-scraper", "t1") as dst:
        # Le .env du frontend pointe sur localhost:8000 (développement). S'il
        # entrait dans le contexte de build, le bundle de prod risquerait de
        # partir avec cette URL.
        assert "VITE_API_URL=http://localhost:8000" in (
            dst / "frontend" / ".env"
        ).read_text(encoding="utf-8")
        ignored = set(
            line.strip()
            for line in (dst / "frontend" / ".dockerignore")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        assert ".env" in ignored
        assert "node_modules" in ignored


# --- Routage SPA -----------------------------------------------------------


def test_serve_falls_back_to_index_for_client_routes():
    body = _render()
    # Sans -s, un rechargement sur /login renverrait un 404 : react-router
    # route côté client, le serveur ne connaît que index.html.
    assert 'CMD ["serve", "-s", "dist", "-l", "3000"]' in body


def test_healthcheck_present():
    body = _render()
    assert "HEALTHCHECK" in body
    assert "--interval=30s" in body


# --- Un seul artefact, indépendant du tier ---------------------------------


def test_frontend_dockerfile_is_identical_across_tiers():
    assert _render("t0") == _render("t1") == _render("t2")
