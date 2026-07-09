"""Logique de monétisation (Phase 3, monetization — services purs).

Règle de rôle premium (active/trialing) + fulfillment d'un achat (token + dates).
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from app.core.models import UserRole  # noqa: E402
from app.modules.monetization.models import Purchase, SubscriptionStatus  # noqa: E402
from app.modules.monetization.services import (  # noqa: E402
    fulfill_purchase,
    role_for_subscription_status,
)


def test_role_premium_for_active_and_trialing():
    assert role_for_subscription_status(SubscriptionStatus.active) == UserRole.premium
    assert role_for_subscription_status(SubscriptionStatus.trialing) == UserRole.premium


def test_role_user_for_non_paying_statuses():
    for status in (
        SubscriptionStatus.past_due,
        SubscriptionStatus.cancelled,
        SubscriptionStatus.unpaid,
    ):
        assert role_for_subscription_status(status) == UserRole.user


def test_fulfill_purchase_sets_token_and_dates():
    purchase = Purchase(product_id=1, email="x@y.com")
    assert purchase.download_token is None
    assert purchase.fulfilled_at is None

    fulfill_purchase(purchase, token_ttl_days=7)

    assert purchase.download_token and len(purchase.download_token) > 40
    assert purchase.fulfilled_at is not None
    assert purchase.token_expires_at > purchase.fulfilled_at
