"""Tool Suno — génération audio via l'API Suno (Chap 15).

Un *tool* du moteur agentic : encapsule un appel d'API externe. Signature
uniforme `async (context, step_def) -> dict`. Le résultat est stocké tel quel
comme sortie de l'étape.

Stub par défaut (aucune clé) : renvoie une URL audio d'exemple **déterministe**,
pour développer et tester sans secret — même patron que `studio/llm.py` et
`monetization/stripe_client.py`. Réel si `SUNO_API_KEY` est présent.
"""

import hashlib
import os

_SAMPLE = "https://cdn.example/suno/{h}.mp3"


async def suno_generate(context: dict, step_def: dict) -> dict:
    params = context.get("parameters", {})
    prompt = {
        "lyrics": context.get("lyrics", ""),
        "style": context.get("style", ""),
        "voice": params.get("voice", ""),
        "rhythm": params.get("rhythm", ""),
        "instruments": params.get("instruments", []),
    }

    if not os.environ.get("SUNO_API_KEY"):
        # Fail-closed : en production, une URL d'exemple facturée en crédits
        # n'est pas un fallback acceptable.
        if os.environ.get("ENVIRONMENT", "").lower() == "production":
            raise RuntimeError(
                "SUNO_API_KEY manquant alors que ENVIRONMENT=production — "
                "refus du mode stub (fail-closed)"
            )
        # Stub : URL stable dérivée du prompt (mêmes entrées -> même URL).
        digest = hashlib.sha256(str(prompt).encode("utf-8")).hexdigest()[:12]
        return {"status": "done", "audio_url": _SAMPLE.format(h=digest), "stub": True}

    # Réel : l'API Suno est asynchrone (submit -> job id -> poll/webhook -> url).
    # Le squelette est laissé à câbler ; le moteur passerait alors le job en
    # `awaiting_callback` et un webhook (POST /webhooks/suno) le reprendrait.
    raise NotImplementedError(
        "Intégration Suno réelle à câbler (SUNO_API_KEY présent) — submit + poll."
    )
