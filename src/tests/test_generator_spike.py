"""Spike du générateur Copier (Phase 2, incrément 0).

Prouve le mécanisme de bout en bout : `copier copy` (API Python) génère un projet
dont le `.env` porte le bon tier, le bon nom de projet, et les flags MODULE_*
**résolus depuis le tier** par le context hook (équivalent réel du _pre du livre).

`unsafe=True` = équivalent de `--trust` : nécessaire car un context hook exécute
du code.
"""

import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
BACKEND = SRC / "backend"
GENERATOR = SRC / "generator"
sys.path.insert(0, str(BACKEND))

from copier import run_copy  # noqa: E402


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
