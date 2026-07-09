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
from app.core.models import User

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
