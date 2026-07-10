"""Dépendances d'authentification FastAPI (Chap 7).

`get_current_user` extrait le Bearer access token, le vérifie, et charge le
`User` correspondant. Utilisé par `/me` et, plus tard, par les guards de rôle.
"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.security import decode_token
from app.core.database import get_db
from app.core.models import User, UserRole

# Hiérarchie des rôles (Chap 7) : du moins au plus privilégié.
ROLE_ORDER: tuple[str, ...] = ("anonymous", "waitlist", "user", "premium", "admin")


def role_rank(role: "UserRole | str") -> int:
    value = role.value if isinstance(role, UserRole) else role
    return ROLE_ORDER.index(value)


_bearer = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Non authentifié",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise _UNAUTHENTICATED
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except jwt.InvalidTokenError:
        raise _UNAUTHENTICATED

    user = await db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise _UNAUTHENTICATED
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Guard : réserve l'endpoint au rôle `admin`."""
    if user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Réservé aux administrateurs",
        )
    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Comme get_current_user mais renvoie None au lieu de lever 401.

    Utile pour les endpoints à accès mixte (contenu public + premium) où la
    présence d'un utilisateur module la réponse sans être obligatoire.
    """
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except jwt.InvalidTokenError:
        return None
    user = await db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        return None
    return user
