"""Client LLM du Studio — sortie structurée (JSON), config-gated (Chap 24).

Réel via le LLM proxy partagé (LLM_PROXY_URL, API compatible OpenAI, mode JSON)
si configuré ; sinon retombe sur le `stub` déterministe fourni par l'agent.
Aucun appel réseau en dev/test.
"""

import json
import os
from collections.abc import Callable


def generate(model: str, prompt: str, stub: Callable[[], dict]) -> dict:
    base_url = os.environ.get("LLM_PROXY_URL", "")
    if not base_url:
        # Fail-closed : une vitrine « art-dirigée » par le stub ne doit jamais
        # partir en production silencieusement.
        if os.environ.get("ENVIRONMENT", "").lower() == "production":
            raise RuntimeError(
                "LLM_PROXY_URL manquant alors que ENVIRONMENT=production — "
                "refus du mode stub (fail-closed)"
            )
        return stub()

    from openai import OpenAI  # import paresseux : dépend d'openai en prod

    client = OpenAI(base_url=base_url, api_key=os.environ.get("LLM_PROXY_TOKEN", "x"))
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        # Pas de temperature fixe : claude-opus-5 (routé via llm-proxy) ne
        # supporte que temperature=1, contrairement à d'autres modèles — la
        # sortie est de toute façon validée par les guardrails (chap 24), la
        # créativité n'a pas besoin d'être bridée côté client.
    )
    return json.loads(response.choices[0].message.content or "{}")
