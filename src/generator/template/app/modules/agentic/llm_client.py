"""Client LLM (Chap 15/18).

Route tous les appels IA par le LLM proxy partagé (LiteLLM), qui expose une API
compatible OpenAI. Configuré via LLM_PROXY_URL / LLM_PROXY_TOKEN (token de projet
avec quota). Sans configuration, retombe sur une réponse simulée déterministe —
pratique en dev/test, jamais d'appel réseau.
"""

import os


def call_llm(model: str, messages: list[dict], temperature: float = 0.3) -> str:
    base_url = os.environ.get("LLM_PROXY_URL", "")
    if not base_url:
        # Fail-closed : en production, servir le stub reviendrait à facturer des
        # crédits pour des réponses simulées.
        if os.environ.get("ENVIRONMENT", "").lower() == "production":
            raise RuntimeError(
                "LLM_PROXY_URL manquant alors que ENVIRONMENT=production — "
                "refus du mode stub (fail-closed)"
            )
        last = messages[-1]["content"] if messages else ""
        return f"[stub:{model}] réponse simulée à: {last}"

    from openai import OpenAI  # import paresseux : dépend d'openai en prod

    client = OpenAI(base_url=base_url, api_key=os.environ.get("LLM_PROXY_TOKEN", "x"))
    response = client.chat.completions.create(
        model=model, messages=messages, temperature=temperature
    )
    return response.choices[0].message.content or ""
