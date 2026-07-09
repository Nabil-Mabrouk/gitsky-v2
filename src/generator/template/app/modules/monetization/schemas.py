"""Schémas Pydantic du module monetization (Chap 5)."""

from pydantic import BaseModel, ConfigDict


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    price_cents: int


class ProductCreate(BaseModel):
    name: str
    slug: str
    price_cents: int
    stripe_price_id: str = ""
    file_path: str = ""


class CheckoutRequest(BaseModel):
    product_slug: str


class CheckoutResponse(BaseModel):
    checkout_url: str


class SubscriptionStatusRead(BaseModel):
    status: str | None
