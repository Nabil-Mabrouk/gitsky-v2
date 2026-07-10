"""Routeurs du module monetization (Chap 16).

- shop_router (/api/shop) : catalogue, checkout, download (cascade), webhook.
- admin_router (/api/admin/shop) : création de produits.
- subscription_router (/api/subscription) : statut de l'abonnement courant.

Architecture webhook-first : le fulfillment ne se fie pas à la redirection mais
aux événements Stripe. Client Stripe stubbé.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_current_user, require_admin
from app.core.database import get_db
from app.core.models import User
from app.modules.monetization.models import (
    Product,
    Purchase,
    Subscription,
    SubscriptionStatus,
)
from app.modules.monetization.schemas import (
    CheckoutRequest,
    CheckoutResponse,
    ProductCreate,
    ProductRead,
    SubscriptionStatusRead,
)
from app.modules.monetization.services import (
    fulfill_purchase,
    role_for_subscription_status,
)
from app.modules.monetization.stripe_client import (
    create_checkout_session,
    verify_webhook,
)

shop_router = APIRouter()
admin_router = APIRouter()
subscription_router = APIRouter()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --- Boutique -------------------------------------------------------------

@shop_router.get("/products", response_model=list[ProductRead])
async def list_products(db: AsyncSession = Depends(get_db)) -> list[Product]:
    result = await db.execute(select(Product).where(Product.is_active.is_(True)))
    return list(result.scalars().all())


@shop_router.post("/checkout", response_model=CheckoutResponse)
async def checkout(
    payload: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CheckoutResponse:
    product = (
        await db.execute(select(Product).where(Product.slug == payload.product_slug))
    ).scalar_one_or_none()
    if product is None or not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Produit introuvable"
        )
    session = create_checkout_session(product.slug, user.email)
    db.add(
        Purchase(
            user_id=user.id,
            product_id=product.id,
            email=user.email,
            stripe_session_id=session["id"],
        )
    )
    await db.commit()
    return CheckoutResponse(checkout_url=session["url"])


@shop_router.get("/download/{token}")
async def download(token: str, db: AsyncSession = Depends(get_db)) -> dict:
    purchase = (
        await db.execute(select(Purchase).where(Purchase.download_token == token))
    ).scalar_one_or_none()
    # Vérifications en cascade (Chap 16).
    if purchase is None or purchase.fulfilled_at is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if purchase.token_expires_at and _utcnow() > purchase.token_expires_at:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Lien expiré")
    if purchase.download_count >= purchase.max_downloads:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Limite atteinte")

    purchase.download_count += 1
    await db.commit()
    # En prod : FileResponse(purchase.product.file_path).
    return {"status": "ok", "download_count": purchase.download_count}


@shop_router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    payload = await request.body()
    event = verify_webhook(payload, request.headers.get("stripe-signature"), "")

    etype = event.get("type")
    obj = event.get("data", {}).get("object", {})

    if etype == "checkout.session.completed":
        purchase = (
            await db.execute(
                select(Purchase).where(Purchase.stripe_session_id == obj.get("id"))
            )
        ).scalar_one_or_none()
        if purchase is not None and purchase.fulfilled_at is None:
            fulfill_purchase(purchase)
            await db.commit()

    elif etype in ("customer.subscription.created", "customer.subscription.updated"):
        await _sync_subscription(db, obj)

    elif etype == "customer.subscription.deleted":
        obj = {**obj, "status": SubscriptionStatus.cancelled.value}
        await _sync_subscription(db, obj)

    return {"received": True}


async def _sync_subscription(db: AsyncSession, obj: dict) -> None:
    user_id = obj.get("user_id")
    sub_status = SubscriptionStatus(obj["status"])
    subscription = (
        await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    ).scalar_one_or_none()
    if subscription is None:
        db.add(
            Subscription(
                user_id=user_id,
                stripe_subscription_id=obj.get("id"),
                status=sub_status,
            )
        )
    else:
        subscription.status = sub_status

    # Règle : active/trialing -> premium, sinon user (Chap 16).
    user = await db.get(User, user_id)
    if user is not None:
        user.role = role_for_subscription_status(sub_status)
    await db.commit()


# --- Admin ----------------------------------------------------------------

@admin_router.post(
    "/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED
)
async def create_product(
    payload: ProductCreate,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Product:
    product = Product(
        name=payload.name,
        slug=payload.slug,
        price_cents=payload.price_cents,
        stripe_price_id=payload.stripe_price_id,
        file_path=payload.file_path,
        is_active=True,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


# --- Abonnement -----------------------------------------------------------

@subscription_router.get("/status", response_model=SubscriptionStatusRead)
async def subscription_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionStatusRead:
    subscription = (
        await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    ).scalar_one_or_none()
    return SubscriptionStatusRead(
        status=subscription.status.value if subscription else None
    )
