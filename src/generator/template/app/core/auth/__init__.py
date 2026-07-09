"""Module core `auth` (Chap 7).

Actif dès le tier T1 (`MODULE_AUTH=true`). Ce paquet fournit les primitives de
sécurité (hachage argon2, JWT access/refresh) ; le routeur FastAPI est ajouté
dans un incrément ultérieur.
"""

from app.core.auth.router import router
from app.core.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

__all__ = [
    "router",
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
]
