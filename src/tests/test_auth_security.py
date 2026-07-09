"""Primitives de sécurité auth (Phase 1, incrément 4a).

Couvre le hachage argon2 (round-trip, sel, échec) et les JWT access/refresh
(round-trip, distinction de type, expiration, altération).
"""

import sys
from datetime import timedelta
from pathlib import Path

import jwt
import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.auth import (  # noqa: E402
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


# --- Hachage argon2 -------------------------------------------------------

def test_hash_verify_roundtrip():
    hashed = hash_password("s3cret!")
    assert hashed != "s3cret!"  # jamais en clair
    assert hashed.startswith("$argon2")  # bien de l'argon2
    assert verify_password("s3cret!", hashed) is True


def test_verify_rejects_wrong_password():
    hashed = hash_password("s3cret!")
    assert verify_password("wrong", hashed) is False


def test_hash_is_salted():
    # Deux hachages du même mot de passe diffèrent (sel aléatoire).
    assert hash_password("same") != hash_password("same")


# --- JWT access / refresh -------------------------------------------------

def test_access_token_roundtrip():
    token = create_access_token(42, role="admin")
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "42"
    assert payload["type"] == "access"
    assert payload["role"] == "admin"


def test_refresh_token_type():
    token = create_refresh_token(7)
    payload = decode_token(token, expected_type="refresh")
    assert payload["type"] == "refresh"


def test_wrong_expected_type_rejected():
    access = create_access_token(1)
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(access, expected_type="refresh")


def test_expired_token_rejected():
    expired = create_access_token(1, expires_delta=timedelta(seconds=-1))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(expired)


def test_tampered_token_rejected():
    token = create_access_token(1)
    tampered = token[:-3] + ("aaa" if token[-3:] != "aaa" else "bbb")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(tampered)
