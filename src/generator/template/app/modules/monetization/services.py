"""Logique métier de monétisation (Chap 16) — pure, sans I/O réseau.

- `role_for_subscription_status` : règle rôle premium (active/trialing) sinon user.
- `fulfill_purchase` : pose le token de téléchargement + les dates (appelé par le
  webhook `checkout.session.completed`).
"""

import secrets
from datetime import datetime, timedelta, timezone

from app.core.models import UserRole
from app.modules.monetization.models import Purchase, SubscriptionStatus

_PREMIUM_STATUSES = {SubscriptionStatus.active, SubscriptionStatus.trialing}


def role_for_subscription_status(status: SubscriptionStatus) -> UserRole:
    return UserRole.premium if status in _PREMIUM_STATUSES else UserRole.user


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def fulfill_purchase(purchase: Purchase, token_ttl_days: int = 7) -> None:
    """Rend un achat téléchargeable : token aléatoire + dates. Idempotent-safe."""
    purchase.download_token = secrets.token_urlsafe(48)
    purchase.fulfilled_at = _utcnow()
    purchase.token_expires_at = purchase.fulfilled_at + timedelta(days=token_ttl_days)
