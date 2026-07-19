"""Routeurs monetization de bout en bout (Phase 3, monetization — API).

Boutique (catalogue, admin, checkout, download cascade), webhook fulfillment,
et synchro de rôle d'abonnement. Base SQLite fichier injectée par override.
"""

import asyncio
import atexit
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.models  # noqa: E402,F401
import app.modules.monetization.models  # noqa: E402,F401
from app.core.auth.security import create_access_token, hash_password  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.models import User, UserRole  # noqa: E402
from app.modules.monetization import (  # noqa: E402
    admin_router,
    shop_router,
    subscription_router,
)
from app.modules.monetization.models import Product, Purchase  # noqa: E402

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_monetization_{os.getpid()}.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}")
factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

SEED: dict[str, int] = {}


def _naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        admin = User(email="a@x.com", hashed_password=hash_password("x"), role=UserRole.admin)
        user = User(email="u@x.com", hashed_password=hash_password("x"), role=UserRole.user)
        product = Product(name="Guide FastAPI", slug="guide", price_cents=2900, is_active=True)
        db.add_all([admin, user, product])
        await db.commit()
        await db.refresh(admin)
        await db.refresh(user)
        await db.refresh(product)
        SEED.update(admin_id=admin.id, user_id=user.id, product_id=product.id)

        future = _naive_now() + timedelta(days=7)
        past = _naive_now() - timedelta(days=1)
        db.add_all(
            [
                Purchase(product_id=product.id, email="u@x.com", download_token="tok-ok",
                         fulfilled_at=_naive_now(), token_expires_at=future,
                         download_count=0, max_downloads=5),
                Purchase(product_id=product.id, email="u@x.com", download_token="tok-expired",
                         fulfilled_at=_naive_now(), token_expires_at=past,
                         download_count=0, max_downloads=5),
                Purchase(product_id=product.id, email="u@x.com", download_token="tok-limit",
                         fulfilled_at=_naive_now(), token_expires_at=future,
                         download_count=5, max_downloads=5),
            ]
        )
        await db.commit()


asyncio.run(_seed())


async def _override_get_db():
    async with factory() as session:
        yield session


app = FastAPI()
app.include_router(shop_router, prefix="/api/shop")
app.include_router(admin_router, prefix="/api/admin/shop")
app.include_router(subscription_router, prefix="/api/subscription")
app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)


@atexit.register
def _cleanup() -> None:
    asyncio.run(engine.dispose())
    try:
        _DB_FILE.unlink()
    except OSError:
        pass


def _auth(user_id: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


async def _purchase_by_session(session_id: str) -> Purchase | None:
    async with factory() as db:
        return (
            await db.execute(select(Purchase).where(Purchase.stripe_session_id == session_id))
        ).scalar_one_or_none()


async def _user_role(user_id: int) -> UserRole:
    async with factory() as db:
        return (await db.get(User, user_id)).role


# --- Boutique -------------------------------------------------------------

def test_products_public():
    r = client.get("/api/shop/products")
    assert r.status_code == 200
    assert any(p["slug"] == "guide" for p in r.json())


def test_admin_create_product_requires_admin():
    payload = {"name": "Ebook", "slug": "ebook", "price_cents": 1500}
    assert client.post("/api/admin/shop/products", json=payload).status_code == 401
    assert (
        client.post("/api/admin/shop/products", json=payload, headers=_auth(SEED["user_id"])).status_code
        == 403
    )
    r = client.post("/api/admin/shop/products", json=payload, headers=_auth(SEED["admin_id"]))
    assert r.status_code == 201
    assert r.json()["slug"] == "ebook"


def test_download_cascade():
    # Token inconnu -> 404.
    assert client.get("/api/shop/download/inconnu").status_code == 404
    # Lien expiré -> 410.
    assert client.get("/api/shop/download/tok-expired").status_code == 410
    # Limite atteinte -> 410.
    assert client.get("/api/shop/download/tok-limit").status_code == 410
    # Valide -> 200, compteur incrémenté.
    r = client.get("/api/shop/download/tok-ok")
    assert r.status_code == 200
    assert r.json()["download_count"] == 1


def test_checkout_then_webhook_fulfills():
    # Checkout crée un achat en attente (non fulfilled).
    r = client.post(
        "/api/shop/checkout",
        json={"product_slug": "guide"},
        headers=_auth(SEED["user_id"]),
    )
    assert r.status_code == 200
    assert r.json()["checkout_url"]

    session_id = "cs_stub_guide"  # id déterministe du stub
    purchase = asyncio.run(_purchase_by_session(session_id))
    assert purchase is not None
    assert purchase.fulfilled_at is None  # pas encore payé

    # Webhook Stripe : paiement complété -> fulfillment.
    event = {
        "type": "checkout.session.completed",
        "data": {"object": {"id": session_id}},
    }
    assert client.post("/api/shop/webhook", json=event).status_code == 200

    purchase = asyncio.run(_purchase_by_session(session_id))
    assert purchase.fulfilled_at is not None
    assert purchase.download_token  # devient téléchargeable


# --- Abonnement -----------------------------------------------------------

def test_subscription_webhook_grants_premium():
    # Forme RÉELLE d'un événement Stripe : nos identifiants ne voyagent que
    # dans metadata (posé au checkout), jamais en champ direct de l'objet.
    assert asyncio.run(_user_role(SEED["user_id"])) == UserRole.user

    event = {
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_1",
                "status": "active",
                "metadata": {"user_id": str(SEED["user_id"])},
            }
        },
    }
    assert client.post("/api/shop/webhook", json=event).status_code == 200

    # Le rôle passe premium, et le statut est visible.
    assert asyncio.run(_user_role(SEED["user_id"])) == UserRole.premium
    r = client.get("/api/subscription/status", headers=_auth(SEED["user_id"]))
    assert r.status_code == 200
    assert r.json()["status"] == "active"


def test_subscription_webhook_without_metadata_is_ignored():
    # Événement sans metadata.user_id (webhook mal câblé, abonnement créé hors
    # checkout) : impossible de relier un compte -> ignoré, aucun rôle modifié.
    event = {
        "type": "customer.subscription.updated",
        "data": {"object": {"id": "sub_orphan", "status": "active"}},
    }
    assert client.post("/api/shop/webhook", json=event).status_code == 200
    assert asyncio.run(_user_role(SEED["admin_id"])) == UserRole.admin
