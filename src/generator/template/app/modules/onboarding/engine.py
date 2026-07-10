"""Moteur de scoring d'onboarding (Chap 12) — logique PURE, pilotée par JSON.

Les règles métier vivent dans des flows JSON (`flows/*.json`), modifiables sans
toucher au code. `evaluate_scoring` évalue les règles dans l'ordre et retourne la
première correspondance, ou le `default`. Pureté = testabilité exhaustive.
"""

import json
from pathlib import Path

_FLOWS_DIR = Path(__file__).resolve().parent / "flows"


class FlowNotFound(Exception):
    """Flow d'onboarding introuvable."""


def load_flow(flow_id: str) -> dict:
    path = _FLOWS_DIR / f"{flow_id}.json"
    if not path.is_file():
        raise FlowNotFound(flow_id)
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_scoring(flow: dict, answers: dict[str, str]) -> dict:
    for rule in flow["scoring"]["rules"]:
        if all(answers.get(k) == v for k, v in rule["conditions"].items()):
            return rule["result"]
    return flow["scoring"]["default"]


def load_result_screen(flow: dict, profile: str) -> dict:
    """Config visuelle (titre, description, label) associée au profil calculé."""
    return flow.get("screens", {}).get(profile, {})
