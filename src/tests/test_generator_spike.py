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
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
BACKEND = SRC / "backend"
GENERATOR = SRC / "generator"
sys.path.insert(0, str(BACKEND))

from copier import run_copy  # noqa: E402

# Le context hook est aussi testé unitairement (logique pure, sans Copier).
sys.path.insert(0, str(GENERATOR / "extensions"))
import context as ctx  # noqa: E402


def _generate(
    tier: str, name: str, dst: Path, modules: dict | None = None
) -> set[str]:
    data: dict = {"project_name": name, "gitsky_tier": tier}
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
            "project_name": "pain-scraper",
            "gitsky_tier": "t1",
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


def _rmtree_robuste(path: Path) -> None:
    # Un .git sous Windows contient des fichiers en lecture seule -> rmtree
    # échoue ; on remet le bit d'écriture puis on réessaie.
    def _onexc(func, p, exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    shutil.rmtree(path, onexc=_onexc)


def test_tasks_provision_register_and_git_init():
    tmp = Path(tempfile.mkdtemp())
    try:
        dst = tmp / "proj"
        run_copy(
            str(GENERATOR),
            str(dst),
            data={"project_name": "pain-scraper", "gitsky_tier": "t1"},
            defaults=True,
            quiet=True,
            unsafe=True,
        )
        # Task provision_db (SIMULÉE).
        prov = json.loads((dst / ".gitsky" / "provisioned.json").read_text("utf-8"))
        assert prov["database"] == "pain-scraper_db"
        assert prov["status"] == "simulated"
        # Task register_fleet (SIMULÉE).
        fleet = json.loads((dst / ".gitsky" / "fleet.json").read_text("utf-8"))
        assert fleet["project"] == "pain-scraper"
        assert fleet["tier"] == "t1"
        # Task git init + commit initial (RÉELLE).
        assert (dst / ".git").is_dir()
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
                "project_name": "p",
                "gitsky_tier": "t0",
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
