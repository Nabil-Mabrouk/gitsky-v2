"""Modèles du module `monetization` (Chap 4 / Chap 16).

Boutique (Product/Purchase, achat unique) + abonnements (Subscription, récurrent).
Deux flags indépendants : MODULE_MONETIZATION_SHOP / _SUBSCRIPTION.
"""

import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
)

from app.core.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    price_cents = Column(Integer, nullable=False)  # 2900 = 29,00 €
    stripe_price_id = Column(String)
    file_path = Column(String)
    is_active = Column(Boolean, default=True, nullable=False)


class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # null = invité
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    email = Column(String, nullable=False)
    stripe_session_id = Column(String, unique=True)
    download_token = Column(String, unique=True)
    download_count = Column(Integer, default=0, nullable=False)
    max_downloads = Column(Integer, default=5, nullable=False)
    token_expires_at = Column(DateTime(timezone=True))
    fulfilled_at = Column(DateTime(timezone=True))  # posé par le webhook


class SubscriptionStatus(str, enum.Enum):
    trialing = "trialing"
    active = "active"
    past_due = "past_due"
    cancelled = "cancelled"
    unpaid = "unpaid"


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    stripe_subscription_id = Column(String, unique=True)
    stripe_customer_id = Column(String)
    stripe_price_id = Column(String)
    status = Column(Enum(SubscriptionStatus), nullable=False)
    current_period_end = Column(DateTime(timezone=True))
    trial_end = Column(DateTime(timezone=True))
    cancelled_at = Column(DateTime(timezone=True))
