"""Routeur d'authentification (Chap 7).

Endpoints : register / login / refresh / me.
Stratégie hybride : access token (JWT court) renvoyé dans le corps pour le
frontend ; refresh token (long) posé dans un cookie **HttpOnly** — jamais exposé
au JavaScript (protection XSS).
"""

import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_current_user
from app.core.auth.schemas import Credentials, RegisterRequest, Token, UserRead
from app.core.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.config import get_settings
from app.core.database import get_db
from app.core.models import User

router = APIRouter()
settings = get_settings()

REFRESH_COOKIE = "refresh_token"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
        max_age=settings.refresh_token_expire_days * 86_400,
        path="/api/auth",
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> User:
    exists = (
        await db.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email déjà enregistré"
        )
    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(
    payload: Credentials,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> Token:
    user = (
        await db.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Identifiants invalides"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Compte inactif"
        )

    # Le refresh embarque la version de token du compte (claim `tv`) :
    # incrémenter user.token_version révoque tous les refresh déjà émis.
    _set_refresh_cookie(
        response, create_refresh_token(user.id, tv=user.token_version)
    )
    return Token(access_token=create_access_token(user.id, role=user.role.value))


@router.post("/refresh", response_model=Token)
async def refresh(
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    db: AsyncSession = Depends(get_db),
) -> Token:
    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token manquant"
        )
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token invalide"
        )

    user = await db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilisateur invalide"
        )
    # Révocation : un refresh émis avant le dernier logout-all porte un `tv`
    # périmé — il est refusé même si sa signature et son expiration sont
    # valides. Seule défense possible contre un JWT stateless volé.
    if payload.get("tv", 0) != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token révoqué"
        )
    return Token(access_token=create_access_token(user.id, role=user.role.value))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    """Expire le cookie refresh HttpOnly.

    Sans cet endpoint, « se déconnecter » ne vidait que le localStorage : le
    refresh restait valable 7 jours sur la machine. Volontairement sans auth —
    il doit fonctionner même avec un access token déjà expiré.
    """
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Révoque TOUS les refresh tokens du compte (« déconnexion partout »).

    /logout ne supprime que le cookie du navigateur courant : un refresh copié
    avant (machine compromise) resterait valable 7 jours. Incrémenter
    token_version périme le claim `tv` de tous les refresh émis.
    """
    current_user.token_version += 1
    await db.commit()
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
