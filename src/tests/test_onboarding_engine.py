"""Moteur de scoring onboarding (Phase 3, onboarding — engine).

Logique pure pilotée par le flow JSON : première règle correspondante, sinon
default. Couvre chargement, règles, défaut, et écran de résultat.
"""

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from app.modules.onboarding.engine import (  # noqa: E402
    FlowNotFound,
    evaluate_scoring,
    load_flow,
    load_result_screen,
)


def test_load_flow_ok():
    flow = load_flow("user_profiling")
    assert "questions" in flow
    assert "scoring" in flow


def test_load_flow_missing_raises():
    with pytest.raises(FlowNotFound):
        load_flow("does_not_exist")


def test_scoring_matches_first_rule():
    flow = load_flow("user_profiling")
    result = evaluate_scoring(
        flow, {"role": "dev", "team_size": "solo", "goal": "speed"}
    )
    assert result == {"profile": "solo_builder", "score": 80}


def test_scoring_matches_second_rule():
    flow = load_flow("user_profiling")
    result = evaluate_scoring(
        flow, {"role": "pm", "team_size": "large", "goal": "quality"}
    )
    assert result["profile"] == "quality_pm"


def test_scoring_falls_back_to_default():
    flow = load_flow("user_profiling")
    result = evaluate_scoring(flow, {"role": "designer"})
    assert result == {"profile": "explorer", "score": 30}


def test_result_screen_lookup():
    flow = load_flow("user_profiling")
    screen = load_result_screen(flow, "solo_builder")
    assert screen["title"] == "Solo Builder"
    # Profil inconnu -> écran vide (pas d'erreur).
    assert load_result_screen(flow, "inconnu") == {}
