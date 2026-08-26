"""Vérification de signature webhook GitHub (Chap 26, Phase D).

Fonction pure — même style de test que test_publish.py pour
evaluate_promotion : pas de FastAPI ici, juste hmac.
"""

import hashlib
import hmac
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from app.modules.fleet.github_integration import (  # noqa: E402
    is_deploy_push,
    verify_webhook_signature,
)

SECRET = "s3cret-webhook"
PAYLOAD = b'{"ref": "refs/heads/main"}'


def _sign(payload: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_valid_signature_is_accepted():
    header = _sign(PAYLOAD, SECRET)
    assert verify_webhook_signature(PAYLOAD, header, SECRET) is True


def test_signature_with_wrong_secret_is_rejected():
    header = _sign(PAYLOAD, "autre-secret")
    assert verify_webhook_signature(PAYLOAD, header, SECRET) is False


def test_signature_for_different_payload_is_rejected():
    header = _sign(b'{"ref": "refs/heads/other"}', SECRET)
    assert verify_webhook_signature(PAYLOAD, header, SECRET) is False


def test_missing_header_is_rejected():
    assert verify_webhook_signature(PAYLOAD, None, SECRET) is False


def test_missing_secret_is_rejected():
    header = _sign(PAYLOAD, SECRET)
    assert verify_webhook_signature(PAYLOAD, header, "") is False


def test_header_without_sha256_prefix_is_rejected():
    digest = hmac.new(SECRET.encode(), PAYLOAD, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(PAYLOAD, digest, SECRET) is False  # pas de "sha256="


# --- is_deploy_push : seul un push sur la branche de déploiement compte ----


def test_push_to_deploy_branch_triggers_deploy():
    payload = b'{"ref": "refs/heads/main"}'
    assert is_deploy_push("push", payload, "main") is True


def test_push_to_feature_branch_does_not_trigger_deploy():
    payload = b'{"ref": "refs/heads/feature/wip-thing"}'
    assert is_deploy_push("push", payload, "main") is False


def test_push_to_configured_non_default_deploy_branch():
    payload = b'{"ref": "refs/heads/production"}'
    assert is_deploy_push("push", payload, "production") is True
    assert is_deploy_push("push", payload, "main") is False


def test_non_push_event_never_triggers_deploy_even_on_deploy_branch():
    payload = b'{"ref": "refs/heads/main"}'
    assert is_deploy_push("ping", payload, "main") is False
    assert is_deploy_push(None, payload, "main") is False


def test_malformed_or_missing_ref_does_not_trigger_and_does_not_raise():
    assert is_deploy_push("push", b"not json", "main") is False
    assert is_deploy_push("push", b"{}", "main") is False
    assert is_deploy_push("push", b"[]", "main") is False
