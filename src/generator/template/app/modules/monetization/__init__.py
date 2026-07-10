"""Module `monetization` — boutique + abonnements Stripe (Chap 16).

Trois routeurs : shop (/api/shop), admin (/api/admin/shop), subscription
(/api/subscription). Webhook-first ; client Stripe stubbé.
"""

from app.modules.monetization.router import (
    admin_router,
    shop_router,
    subscription_router,
)

__all__ = ["shop_router", "admin_router", "subscription_router"]
