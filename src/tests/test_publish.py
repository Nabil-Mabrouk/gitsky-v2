"""Modèle de publication — logique pure (Phase 6 — sans tiers, Chap 24).

Barre l'étape irréversible (live), pas la génération. Sous-domaine de la
flotte (jetable, `.mystudio.com`) : auto-live si guardrails OK. Domaine dédié :
approbation humaine obligatoire.
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from app.modules.fleet.publish import evaluate_promotion  # noqa: E402

FLEET_DOMAIN = "pain-scraper.mystudio.com"
DEDICATED_DOMAIN = "pain-scraper.com"


def test_draft_to_preview_always_allowed():
    d = evaluate_promotion("draft", FLEET_DOMAIN, guardrails_pass=True)
    assert d["allowed"] and d["target"] == "preview"


def test_preview_to_live_auto_on_fleet_subdomain_when_guardrails_pass():
    d = evaluate_promotion("preview", FLEET_DOMAIN, guardrails_pass=True)
    assert d["allowed"] and d["target"] == "live"


def test_preview_to_live_blocked_when_guardrails_fail():
    assert not evaluate_promotion("preview", FLEET_DOMAIN, guardrails_pass=False)["allowed"]


def test_preview_to_live_dedicated_domain_requires_human():
    assert not evaluate_promotion(
        "preview", DEDICATED_DOMAIN, True, human_approved=False
    )["allowed"]
    assert evaluate_promotion(
        "preview", DEDICATED_DOMAIN, True, human_approved=True
    )["allowed"]


def test_live_is_terminal():
    assert not evaluate_promotion("live", FLEET_DOMAIN, guardrails_pass=True)["allowed"]
