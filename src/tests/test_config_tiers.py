"""Flags MODULE_* (Phase 6 — catalogue de modules, Chap 2).

Chaque flag est un booléen indépendant, par défaut désactivé (aucun profil,
aucun palier). `auth` est core : toujours actif, jamais un flag MODULE_*.

On instancie `Settings` directement avec des kwargs (priorité maximale dans
pydantic-settings) pour tester en process, sans dépendre de l'environnement.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generator" / "template"))

from app.core.config import MODULE_FLAGS, Settings  # noqa: E402


def flags(s: Settings) -> dict[str, bool]:
    return {f: getattr(s, f) for f in MODULE_FLAGS}


def test_auth_is_core_not_a_module_flag():
    assert "module_auth" not in MODULE_FLAGS


def test_all_flags_off_by_default():
    s = Settings()
    assert all(v is False for v in flags(s).values())
    # auth reste actif malgré tout : c'est core, pas un flag.
    assert s.enabled_modules == ["auth"]


def test_each_flag_is_independently_settable():
    s = Settings(module_admin=True, module_agentic=True)
    assert s.module_admin is True
    assert s.module_agentic is True
    # Rien d'autre ne s'active en cascade : pas de profil, pas de dérivation.
    assert s.module_analytics is False
    assert s.module_monetization_shop is False


def test_enabled_modules_lists_auth_plus_active_flags():
    s = Settings(module_admin=True, module_i18n=True)
    assert s.enabled_modules == ["auth", "admin", "i18n"]


def test_all_flags_can_be_enabled_at_once():
    s = Settings(**{flag: True for flag in MODULE_FLAGS})
    assert all(v is True for v in flags(s).values())
    assert set(s.enabled_modules) == {"auth"} | {
        f.removeprefix("module_") for f in MODULE_FLAGS
    }
