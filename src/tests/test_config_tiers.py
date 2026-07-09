"""Profils de tier -> flags MODULE_* (Phase 1, incrément 1).

Vérifie que `GITSKY_TIER` résout le bon ensemble de modules (tableau Chap 2 §3)
et que la surcharge explicite d'un flag gagne toujours sur le profil.

On instancie `Settings` directement avec des kwargs (priorité maximale dans
pydantic-settings) pour tester en process, sans dépendre de l'environnement.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generator" / "template"))

from app.core.config import MODULE_FLAGS, Settings  # noqa: E402


def flags(s: Settings) -> dict[str, bool]:
    return {f: getattr(s, f) for f in MODULE_FLAGS}


def test_t0_all_modules_off():
    s = Settings(gitsky_tier="t0")
    assert all(v is False for v in flags(s).values())
    assert s.enabled_modules == []


def test_t1_profile():
    s = Settings(gitsky_tier="t1")
    # Actifs en T1.
    assert s.module_auth is True
    assert s.module_analytics is True
    assert s.module_security_middleware is True
    # Réservés à T2.
    assert s.module_admin is False
    assert s.module_i18n is False
    assert s.module_agentic is False
    assert s.module_monetization_shop is False


def test_t2_profile():
    s = Settings(gitsky_tier="t2")
    expected_on = {
        "module_auth",
        "module_admin",
        "module_analytics",
        "module_onboarding",
        "module_security_middleware",
        "module_i18n",
        "module_agentic",
        "module_monetization_shop",
        "module_monetization_subscription",
    }
    on = {f for f in MODULE_FLAGS if getattr(s, f)}
    assert on == expected_on
    # tutorials = « selon projet » -> désactivé par défaut, activable au besoin.
    assert s.module_tutorials is False


def test_explicit_flag_overrides_tier():
    # T0 (tout off) mais on force agentic + tutorials.
    s = Settings(gitsky_tier="t0", module_agentic=True, module_tutorials=True)
    assert s.module_agentic is True
    assert s.module_tutorials is True
    # Le reste demeure au profil T0.
    assert s.module_auth is False
    assert s.module_analytics is False


def test_explicit_disable_overrides_tier():
    # T2 mais on coupe explicitement la monétisation abonnement.
    s = Settings(gitsky_tier="t2", module_monetization_subscription=False)
    assert s.module_monetization_subscription is False
    assert s.module_monetization_shop is True  # non touché


def test_unknown_tier_defaults_all_off():
    s = Settings(gitsky_tier="tX")
    assert all(v is False for v in flags(s).values())
