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


def _generate(tier: str, name: str, dst: Path) -> set[str]:
    run_copy(
        str(GENERATOR),
        str(dst),
        data={"project_name": name, "gitsky_tier": tier},
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
