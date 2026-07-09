"""Client LLM (Chap 15).

⚠️ STUB. Un projet GitSky n'appelle JAMAIS Anthropic/OpenAI directement : tout
transite par le LLM proxy partagé (LiteLLM) hébergé sur la flotte (Chap 18).
À CONNECTER lors de la passe de dettes — voir la dette explicite du plan.
"""


def call_llm(model: str, messages: list[dict], temperature: float = 0.3) -> str:
    # SIMULÉ : renvoie une réponse déterministe sans appel réseau.
    last = messages[-1]["content"] if messages else ""
    return f"[stub:{model}] réponse simulée à: {last}"
