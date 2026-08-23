"""Génération d'image réelle du Studio (Chap 24, Round B) — hero uniquement.

Même contrat fail-closed que `llm.py` (LLM_PROXY_URL absent -> stub ; absent
ET ENVIRONMENT=production -> RuntimeError, jamais de stub silencieux en prod)
et mêmes variables d'env — le llm-proxy partagé route aussi les images
(DALL-E 3 via litellm, cf. shared_services/litellm-config.yaml).

Fichier séparé de llm.py : forme de réponse différente (b64_json, pas un
message JSON à parser), pas de retrait de fence markdown à faire — même
raison que suno.py est son propre fichier plutôt que noyé ailleurs.
"""

import os

# Plus petit PNG valide connu (1x1, transparent) — stub déterministe unique,
# pas de paramètre stub: Callable comme llm.py (un seul stub sensé possible
# ici, pas besoin d'un callback par site d'appel).
_STUB_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY"
    "42YAAAAASUVORK5CYII="
)


def generate_image(prompt: str, model: str = "dalle-3") -> str:
    base_url = os.environ.get("LLM_PROXY_URL", "")
    if not base_url:
        if os.environ.get("ENVIRONMENT", "").lower() == "production":
            raise RuntimeError(
                "LLM_PROXY_URL manquant alors que ENVIRONMENT=production — "
                "refus du mode stub (fail-closed)"
            )
        return f"data:image/png;base64,{_STUB_PNG_B64}"

    from openai import OpenAI  # import paresseux : dépend d'openai en prod

    client = OpenAI(base_url=base_url, api_key=os.environ.get("LLM_PROXY_TOKEN", "x"))
    # Contrairement à llm.py : capture et relève TOUJOURS en RuntimeError,
    # indépendamment de ENVIRONMENT — une image hero est un enrichissement,
    # pas un risque de sécurité (le fail-closed sur le stub, lui, reste
    # entier ci-dessus). Une panne DALL-E transitoire (rate-limit, content
    # policy) ne doit pas faire échouer le pipeline entier ; c'est à
    # l'appelant (agents.py::media()) de décider de dégrader silencieusement.
    try:
        response = client.images.generate(
            model=model, prompt=prompt, n=1, size="1024x1024", response_format="b64_json"
        )
    except Exception as exc:
        raise RuntimeError(f"Génération d'image échouée pour le modèle {model} : {exc}") from exc
    b64 = response.data[0].b64_json
    if not b64:
        raise RuntimeError(f"Réponse image vide pour le modèle {model}")
    return f"data:image/png;base64,{b64}"
