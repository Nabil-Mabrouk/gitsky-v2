"""Client Stripe (Chap 16).

Utilise le SDK Stripe réel quand configuré (STRIPE_SECRET_KEY /
STRIPE_WEBHOOK_SECRET), sinon retombe sur un comportement simulé déterministe
(dev/test). Le fulfillment reste webhook-first : la signature est vérifiée par
`verify_webhook` quand un secret est présent.
"""

import json
import os


def create_checkout_session(slug: str, email: str) -> dict:
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key:
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
        return json.loads(payload)

    import stripe

    return stripe.Webhook.construct_event(payload, signature, wh_secret)
