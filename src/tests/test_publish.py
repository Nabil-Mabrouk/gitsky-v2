"""Modèle de publication — logique pure (Phase 5, incrément 7).

Barre l'étape irréversible (live), pas la génération. T0 auto-live si guardrails
OK ; T1+ exige une approbation humaine.
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from app.modules.fleet.publish import evaluate_promotion  # noqa: E402


def test_draft_to_preview_always_allowed():
    d = evaluate_promotion("draft", "t0", guardrails_pass=True)
    assert d["allowed"] and d["target"] == "preview"


def test_preview_to_live_t0_auto_when_guardrails_pass():
    d = evaluate_promotion("preview", "t0", guardrails_pass=True)
    assert d["allowed"] and d["target"] == "live"


def test_preview_to_live_blocked_when_guardrails_fail():
    assert not evaluate_promotion("preview", "t0", guardrails_pass=False)["allowed"]


def test_preview_to_live_t1_requires_human():
    assert not evaluate_promotion("preview", "t1", True, human_approved=False)["allowed"]
    assert evaluate_promotion("preview", "t1", True, human_approved=True)["allowed"]


def test_live_is_terminal():
    assert not evaluate_promotion("live", "t0", guardrails_pass=True)["allowed"]
