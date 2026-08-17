"""Spike du générateur Copier (Phase 2, incrément 0).

Prouve le mécanisme de bout en bout : `copier copy` (API Python) génère un projet
dont le `.env` porte le bon tier, le bon nom de projet, et les flags MODULE_*
**résolus depuis le tier** par le context hook (équivalent réel du _pre du livre).

`unsafe=True` = équivalent de `--trust` : nécessaire car un context hook exécute
du code.
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
BACKEND = SRC / "generator" / "template"
GENERATOR = SRC / "generator"
sys.path.insert(0, str(BACKEND))

from copier import run_copy  # noqa: E402

# Le context hook est aussi testé unitairement (logique pure, sans Copier).
sys.path.insert(0, str(GENERATOR / "extensions"))
import context as ctx  # noqa: E402


def _generate(
    tier: str, name: str, dst: Path, modules: dict | None = None
) -> set[str]:
    data: dict = {"project": {"name": name, "tier": tier}}
    if modules is not None:
        data["modules"] = modules
    run_copy(
        str(GENERATOR),
        str(dst),
        data=data,
        defaults=True,
        quiet=True,
        unsafe=True,
    )
    return set((dst / ".env").read_text(encoding="utf-8").splitlines())


def test_generator_t0_all_modules_off():
    with tempfile.TemporaryDirectory() as tmp:
        lines = _generate("t0", "landing-x", Path(tmp) / "proj")
        assert "GITSKY_TIER=t0" in lines
        assert "PROJECT_NAME=landing-x" in lines
        assert "MODULE_AUTH=false" in lines
        assert "MODULE_AGENTIC=false" in lines
        assert "MODULE_MONETIZATION_SUBSCRIPTION=false" in lines
        # CORS (settings.frontend_url) doit matcher l'origine prod, sinon le
        # navigateur bloque silencieusement /api/auth/login (pas d'erreur
        # visible côté UI, juste un fetch qui échoue).
        assert "FRONTEND_URL=https://landing-x.mystudio.com" in lines


def test_generator_t2_resolves_full_profile():
    with tempfile.TemporaryDirectory() as tmp:
        lines = _generate("t2", "saas-y", Path(tmp) / "proj")
        assert "GITSKY_TIER=t2" in lines
        assert "PROJECT_NAME=saas-y" in lines
        assert "MODULE_AUTH=true" in lines
        assert "MODULE_ADMIN=true" in lines
        assert "MODULE_AGENTIC=true" in lines
        assert "MODULE_MONETIZATION_SUBSCRIPTION=true" in lines
        # tutorials « selon projet » -> désactivé par défaut, même en t2.
        assert "MODULE_TUTORIALS=false" in lines
        assert "FRONTEND_URL=https://saas-y.mystudio.com" in lines


def test_override_enables_module_on_t1():
    with tempfile.TemporaryDirectory() as tmp:
        lines = _generate(
            "t1",
            "mvp-z",
            Path(tmp) / "proj",
            modules={"agentic": True, "monetization_subscription": True},
        )
        # Overrides appliqués par-dessus le profil t1.
        assert "MODULE_AGENTIC=true" in lines
        assert "MODULE_MONETIZATION_SUBSCRIPTION=true" in lines
        # Profil t1 conservé pour le reste.
        assert "MODULE_AUTH=true" in lines
        assert "MODULE_ADMIN=false" in lines  # non surchargé, reste off en t1


def test_override_disables_module_on_t2():
    with tempfile.TemporaryDirectory() as tmp:
        lines = _generate(
            "t2",
            "saas-w",
            Path(tmp) / "proj",
            modules={"monetization_subscription": False},
        )
        # L'override peut aussi désactiver un module actif du profil.
        assert "MODULE_MONETIZATION_SUBSCRIPTION=false" in lines
        assert "MODULE_MONETIZATION_SHOP=true" in lines  # non touché


# --- Logique du scaffolding métier (unitaire, sans Copier) ----------------

def test_generator_tiers_match_backend():
    # Les profils vendorisés du générateur DOIVENT rester synchronisés avec le
    # runtime (app.core.config) — source unique garantie par ce test.
    from app.core.config import MODULE_FLAGS as BACKEND_FLAGS
    from app.core.config import TIER_PROFILES as BACKEND_PROFILES

    assert ctx.MODULE_FLAGS == BACKEND_FLAGS
    assert ctx.TIER_PROFILES == BACKEND_PROFILES


def test_pluralize():
    assert ctx._pluralize("Company") == "companies"  # y consonne -> ies
    assert ctx._pluralize("Day") == "days"  # y voyelle -> +s
    assert ctx._pluralize("Box") == "boxes"  # x -> es
    assert ctx._pluralize("Lead") == "leads"


def test_resolve_domain_models_maps_types():
    out = ctx._resolve_domain_models(
        [{"name": "Company", "fields": {"pain_signal": "text", "priority": "int", "weird": "??"}}]
    )
    assert out[0]["table"] == "companies"
    cols = {f["name"]: f["column"] for f in out[0]["fields"]}
    assert cols["pain_signal"] == "Text"
    assert cols["priority"] == "Integer"
    assert cols["weird"] == "String"  # type inconnu -> fallback String


def test_resolve_domain_routes():
    out = ctx._resolve_domain_routes([{"prefix": "/api/pains", "handlers": "pains.py"}])
    assert out[0]["prefix"] == "/api/pains"
    assert out[0]["name"] == "pains"  # dernier segment -> identifiant routeur


# --- Scaffolding app/domain/ de bout en bout ------------------------------

COMPANY = {
    "name": "Company",
    "fields": {"name": "str", "url": "str", "pain_signal": "text", "priority": "int"},
}


def _generate_domain(data_models: list, dst: Path) -> str:
    run_copy(
        str(GENERATOR),
        str(dst),
        data={
            "project": {"name": "pain-scraper", "tier": "t1"},
            "data_models": data_models,
        },
        defaults=True,
        quiet=True,
        unsafe=True,
    )
    return (dst / "app" / "domain" / "models.py").read_text(encoding="utf-8")


def test_domain_models_scaffolded():
    with tempfile.TemporaryDirectory() as tmp:
        src = _generate_domain([COMPANY], Path(tmp) / "proj")
        compile(src, "models.py", "exec")  # doit être du Python valide
        assert "class Company(Base):" in src
        assert '__tablename__ = "companies"' in src
        assert "id = Column(Integer, primary_key=True, index=True)" in src
        assert "pain_signal = Column(Text)" in src
        assert "priority = Column(Integer)" in src


def test_domain_empty_is_valid_python():
    with tempfile.TemporaryDirectory() as tmp:
        src = _generate_domain([], Path(tmp) / "proj")
        compile(src, "models.py", "exec")  # valide même sans modèle
        assert "class " not in src


def _generate_routers(domain_routes: list, dst: Path) -> str:
    run_copy(
        str(GENERATOR),
        str(dst),
        data={
            "project": {"name": "pain-scraper", "tier": "t1"},
            "domain_routes": domain_routes,
        },
        defaults=True,
        quiet=True,
        unsafe=True,
    )
    return (dst / "app" / "domain" / "routers.py").read_text(encoding="utf-8")


def test_domain_routers_scaffolded():
    with tempfile.TemporaryDirectory() as tmp:
        src = _generate_routers(
            [{"prefix": "/api/pains", "handlers": "pains.py"}], Path(tmp) / "proj"
        )
        compile(src, "routers.py", "exec")  # doit être du Python valide
        assert 'pains_router = APIRouter(prefix="/api/pains"' in src
        assert "async def list_pains(" in src


def test_domain_routers_empty_is_valid_python():
    with tempfile.TemporaryDirectory() as tmp:
        src = _generate_routers([], Path(tmp) / "proj")
        compile(src, "routers.py", "exec")  # valide même sans route
        assert "APIRouter(prefix=" not in src


def _rmtree_robuste(path: Path) -> None:
    # Sous Windows, un .git contient des objets en lecture seule ET un handle
    # peut rester brièvement ouvert (processus git qui vient de sortir,
    # antivirus). On rend inscriptible, puis on réessaie le retrait complet
    # avec un court backoff tant que le verrou transitoire n'est pas relâché.
    def _onexc(func, p, exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    for essai in range(5):
        try:
            shutil.rmtree(path, onexc=_onexc)
            return
        except (PermissionError, OSError):
            if essai == 4:
                raise
            time.sleep(0.2 * (essai + 1))


def test_tasks_provision_register_and_git_init():
    tmp = Path(tempfile.mkdtemp())
    try:
        dst = tmp / "proj"
        run_copy(
            str(GENERATOR),
            str(dst),
            data={"project": {"name": "pain-scraper", "tier": "t1"}},
            defaults=True,
            quiet=True,
            unsafe=True,
        )
        # Task provision_db : sans POSTGRES_CONTAINER en test -> skip gracieux.
        prov = json.loads((dst / ".gitsky" / "provisioned.json").read_text("utf-8"))
        assert prov["database"] == "pain_scraper"
        assert prov["status"] == "skipped_no_postgres"
        # Task register_fleet : sans FLEET_URL en test -> skip gracieux.
        fleet = json.loads((dst / ".gitsky" / "fleet.json").read_text("utf-8"))
        assert fleet["name"] == "pain-scraper"
        assert fleet["tier"] == "t1"
        assert fleet["registered"] == "skipped_no_fleet_url"
        # Task git init + commit initial (RÉELLE).
        assert (dst / ".git").is_dir()
    finally:
        _rmtree_robuste(tmp)


def test_generated_project_ships_no_local_artifacts():
    # Copier n'applique ses exclusions par défaut (__pycache__, *.pyc, ...) QUE
    # si le template n'a pas de _subdirectory (copier/_template.py, `exclude`).
    # On en déclare un : sans _exclude explicite dans copier.yml, la liste tombe
    # à [] et chaque projet généré partait avec les .pyc et la base SQLite de
    # développement de la machine qui génère — committés par le `git add -A`
    # des _tasks.
    tmp = Path(tempfile.mkdtemp())
    try:
        dst = tmp / "proj"
        run_copy(
            str(GENERATOR),
            str(dst),
            data={"project": {"name": "pain-scraper", "tier": "t2"}},
            defaults=True,
            quiet=True,
            unsafe=True,
        )
        assert [str(p.relative_to(dst)) for p in dst.rglob("*.pyc")] == []
        assert [str(p.relative_to(dst)) for p in dst.rglob("__pycache__")] == []
        # Bases de dev : jamais les données d'une machine de dev dans un projet.
        assert [str(p.relative_to(dst)) for p in dst.rglob("*.db")] == []
        # Le code applicatif, lui, doit bien être là.
        assert (dst / "app" / "core" / "main.py").is_file()
    finally:
        _rmtree_robuste(tmp)


def test_initial_commit_contains_no_artifacts():
    # Le `git add -A` des _tasks fige l'état livré : si un artefact passe, il
    # entre dans l'historique du projet dès son premier commit.
    tmp = Path(tempfile.mkdtemp())
    try:
        dst = tmp / "proj"
        run_copy(
            str(GENERATOR),
            str(dst),
            data={"project": {"name": "pain-scraper", "tier": "t2"}},
            defaults=True,
            quiet=True,
            unsafe=True,
        )
        suivis = subprocess.run(
            ["git", "ls-files"],
            cwd=dst,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        assert suivis, "le commit initial ne doit pas être vide"
        assert [f for f in suivis if f.endswith(".pyc")] == []
        assert [f for f in suivis if "__pycache__" in f] == []
        assert [f for f in suivis if f.endswith(".db")] == []
    finally:
        _rmtree_robuste(tmp)


def test_domain_accepts_yaml_string_input():
    # Régression : via `--data key=...`, Copier livre la valeur en CHAÎNE (pas
    # en liste). Le hook doit la parser en YAML plutôt qu'itérer ses caractères.
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "proj"
        run_copy(
            str(GENERATOR),
            str(dst),
            data={
                "project": {"name": "p", "tier": "t0"},
                "data_models": '[{"name": "Widget", "fields": {"label": "str"}}]',
            },
            defaults=True,
            quiet=True,
            unsafe=True,
        )
        src = (dst / "app" / "domain" / "models.py").read_text(encoding="utf-8")
        compile(src, "models.py", "exec")
        assert "class Widget(Base):" in src
        assert '__tablename__ = "widgets"' in src


def test_branding_and_traefik_labels():
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "proj"
        run_copy(
            str(GENERATOR),
            str(dst),
            data={
                "project": {"name": "pain-scraper", "tier": "t1"},
                # branding partiel : primary_foreground doit retomber sur le défaut.
                "branding": {"primary_color": "#FF0000", "font_family": "Roboto"},
            },
            defaults=True,
            quiet=True,
            unsafe=True,
        )
        css = (dst / "frontend" / "src" / "theme.css").read_text("utf-8")
        assert "--color-primary: #FF0000;" in css
        assert "Roboto" in css
        assert "--color-primary-foreground: #FFFFFF;" in css  # défaut conservé

        compose = (dst / "docker-compose.yml").read_text("utf-8")
        assert "container_name: pain-scraper_backend" in compose
        # Labels Traefik scopés au projet, pointant vers son domaine par défaut.
        assert "traefik.http.routers.backend-pain-scraper.rule" in compose
        assert "Host(`api.pain-scraper.mystudio.com`)" in compose
        assert "Host(`pain-scraper.mystudio.com`)" in compose  # frontend


def test_full_nested_book_config():
    # Forme imbriquée exacte du config.yaml du livre (Chap 17, pain-scraper).
    config = {
        "project": {
            "name": "pain-scraper",
            "tier": "t1",
            "domain": "pain-scraper.mystudio.com",
        },
        "modules": {"agentic": True},
        "data_models": [
            {"name": "Company", "fields": {"name": "str", "pain_signal": "text"}}
        ],
        "domain_routes": [{"prefix": "/api/pains", "handlers": "pains.py"}],
        "branding": {"primary_color": "#4F46E5", "font_family": "Inter"},
        "fleet": {"register": True, "stripe_account": "mystudio_main"},
    }
    tmp = Path(tempfile.mkdtemp())
    try:
        dst = tmp / "proj"
        run_copy(
            str(GENERATOR),
            str(dst),
            data=config,
            defaults=True,
            quiet=True,
            unsafe=True,
        )
        env = set((dst / ".env").read_text("utf-8").splitlines())
        assert "GITSKY_TIER=t1" in env
        assert "PROJECT_NAME=pain-scraper" in env
        assert "MODULE_AGENTIC=true" in env  # override par-dessus le profil t1
        assert "MODULE_AUTH=true" in env  # profil t1

        compose = (dst / "docker-compose.yml").read_text("utf-8")
        assert "container_name: pain-scraper_backend" in compose
        assert "Host(`api.pain-scraper.mystudio.com`)" in compose

        css = (dst / "frontend" / "src" / "theme.css").read_text("utf-8")
        assert "Inter" in css

        models = (dst / "app" / "domain" / "models.py").read_text("utf-8")
        assert "class Company(Base):" in models

        routers = (dst / "app" / "domain" / "routers.py").read_text("utf-8")
        assert 'pains_router = APIRouter(prefix="/api/pains"' in routers
    finally:
        _rmtree_robuste(tmp)
