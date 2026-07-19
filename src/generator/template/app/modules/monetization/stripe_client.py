"""Client Stripe (Chap 16).

Utilise le SDK Stripe réel quand configuré (STRIPE_SECRET_KEY /
STRIPE_WEBHOOK_SECRET), sinon retombe sur un comportement simulé déterministe
(dev/test). Le fulfillment reste webhook-first : la signature est vérifiée par
`verify_webhook` quand un secret est présent.
"""

import json
import os


def _forbid_stub_in_production(missing: str) -> None:
    """Fail-closed : en production, un secret manquant est une erreur, jamais
    une bascule silencieuse sur le stub (webhooks forgés, checkouts fictifs)."""
    if os.environ.get("ENVIRONMENT", "").lower() == "production":
        raise RuntimeError(
            f"{missing} manquant alors que ENVIRONMENT=production — "
            "refus du mode stub (fail-closed)"
        )


def create_checkout_session(slug: str, email: str) -> dict:
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key:
        _forbid_stub_in_production("STRIPE_SECRET_KEY")
        return {"id": f"cs_stub_{slug}", "url": f"https://checkout.stripe.test/{slug}"}

    import stripe  # import paresseux : dépend du SDK stripe en prod

    stripe.api_key = key
    session = stripe.checkout.Session.create(
        mode="payment",
        customer_email=email,
        line_items=[{"price": slug, "quantity": 1}],
        metadata={"project_name": os.environ.get("PROJECT_NAME", "")},
    )
    return {"id": session.id, "url": session.url}


def verify_webhook(payload: bytes, signature: str | None, secret: str) -> dict:
    wh_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "") or secret
    if not wh_secret:
        # Dev/test : corps déjà supposé validé (relais interne), parse direct.
        # En production ce chemin accepterait des événements FORGÉS (fulfillment
        # gratuit, passage premium arbitraire) : interdit.
        _forbid_stub_in_production("STRIPE_WEBHOOK_SECRET")
        return json.loads(payload)

    import stripe

    return stripe.Webhook.construct_event(payload, signature, wh_secret)
