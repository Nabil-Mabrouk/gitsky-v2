"""Client Stripe (Chap 16).

⚠️ STUB. À CONNECTER à l'API Stripe réelle + à la vérification de signature
webhook (`stripe.Webhook.construct_event`). Voir la dette explicite du plan.
En prod, le fulfillment est webhook-first (on ne se fie pas à la redirection).
"""

import json


def create_checkout_session(slug: str, email: str) -> dict:
    # SIMULÉ : renvoie une session factice sans appel réseau.
    return {
        "id": f"cs_stub_{slug}",
        "url": f"https://checkout.stripe.test/{slug}",
    }


def verify_webhook(payload: bytes, signature: str | None, secret: str) -> dict:
    # SIMULÉ : en prod, vérifie la signature HMAC et rejette tout appel non signé.
    # Ici on parse simplement le corps déjà supposé validé (relais interne).
    return json.loads(payload)
