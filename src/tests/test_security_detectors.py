"""Détecteurs d'intrusion du module security (Phase 3, sécurité — data).

Logique pure : couvre les trois catégories, le cas propre, et la priorité par
sévérité (injection > scanner > path_scan).
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from app.modules.security.detectors import detect_event  # noqa: E402


def test_clean_request_is_none():
    assert detect_event("/api/health", "Mozilla/5.0", "") is None


def test_path_scan_detected():
    ev = detect_event("/.git/config", "curl/8.0", "")
    assert ev["event_type"] == "path_scan"
    assert ev["severity"] == "medium"


def test_scanner_user_agent_detected():
    ev = detect_event("/", "sqlmap/1.7-dev", "")
    assert ev["event_type"] == "scanner_detected"
    assert ev["severity"] == "high"
    assert ev["details"]["tool"] == "sqlmap"


def test_sql_injection_detected():
    ev = detect_event("/search", "Mozilla/5.0", "q=' OR 1=1--")
    assert ev["event_type"] == "injection_attempt"
    assert ev["severity"] == "critical"


def test_xss_injection_detected():
    ev = detect_event("/", "Mozilla/5.0", "name=<script>alert(1)</script>")
    assert ev["event_type"] == "injection_attempt"


def test_template_injection_detected():
    ev = detect_event("/", "Mozilla/5.0", "x={{7*7}}")
    assert ev["event_type"] == "injection_attempt"


def test_injection_takes_priority_over_scanner_and_path():
    # Chemin suspect + scanner UA + injection -> l'injection (critical) l'emporte.
    ev = detect_event("/.git/", "sqlmap", "q=<script>")
    assert ev["event_type"] == "injection_attempt"
    assert ev["severity"] == "critical"
