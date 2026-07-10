"""Modèle de publication (Chap 24) — logique PURE.

On barre l'étape IRRÉVERSIBLE (passage en live), jamais la génération.
draft -> preview (toujours sûr, noindex) -> live (gate guardrails + blast radius).
T0 (sous-domaine jetable) : auto-live si guardrails OK. T1+/domaine dédié :
approbation humaine obligatoire (human-in-the-loop).
"""

from enum import Enum


class PublishState(str, Enum):
    draft = "draft"
    preview = "preview"
    live = "live"


def evaluate_promotion(
    current: str,
    tier: str,
    guardrails_pass: bool,
    human_approved: bool = False,
) -> dict:
    """Renvoie {allowed, target, reason} sans muter d'état."""
    if current == PublishState.draft.value:
        return {
            "allowed": True,
            "target": PublishState.preview.value,
            "reason": "preview noindex, sans risque",
        }

    if current == PublishState.preview.value:
        if not guardrails_pass:
            return {
                "allowed": False,
                "target": PublishState.preview.value,
                "reason": "guardrails en échec — passage en live bloqué",
            }
        # Étape irréversible : gate par blast radius.
        if tier == "t0" or human_approved:
            return {
                "allowed": True,
                "target": PublishState.live.value,
                "reason": "auto (T0 guardrailé)" if tier == "t0" else "approuvé humainement",
            }
        return {
            "allowed": False,
            "target": PublishState.preview.value,
            "reason": "revue humaine requise (blast radius T1+/domaine dédié)",
        }

    return {
        "allowed": False,
        "target": PublishState.live.value,
        "reason": "déjà en live",
    }
