"""Primitives de sécurité auth (Chap 7).

Hachage de mot de passe via **argon2id** (pwdlib) et jetons **JWT** via PyJWT —
choix 2026 pour remplacer passlib (non maintenu) et python-jose (abandonné).

Deux types de jetons signés HS256 avec `settings.secret_key` :
- `access`  : court (15 min), transporté par le frontend pour les appels API ;
- `refresh` : long (7 j), stocké côté backend en cookie HttpOnly.
Le champ `type` du payload empêche d'utiliser un refresh comme access.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

settings = get_settings()

# argon2id avec les paramètres recommandés par pwdlib/OWASP.
_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _password_hash.verify(password, hashed)


def _create_token(
    subject: str | int,
    token_type: str,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(
    subject: str | int,
    expires_delta: timedelta | None = None,
    **extra_claims: Any,
) -> str:
    delta = expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    return _create_token(subject, "access", delta, extra_claims or None)


def create_refresh_token(
    subject: str | int,
    expires_delta: timedelta | None = None,
    **extra_claims: Any,
) -> str:
    delta = expires_delta or timedelta(days=settings.refresh_token_expire_days)
    return _create_token(subject, "refresh", delta, extra_claims or None)


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    """Décode et vérifie un JWT.

    Lève `jwt.ExpiredSignatureError` si expiré, `jwt.InvalidTokenError` si la
    signature est invalide ou si `expected_type` ne correspond pas au champ
    `type` du payload.
    """
    payload = jwt.decode(
        token, settings.secret_key, algorithms=[settings.jwt_algorithm]
    )
    if expected_type is not None and payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(
            f"type de jeton attendu {expected_type!r}, reçu {payload.get('type')!r}"
        )
    return payload
