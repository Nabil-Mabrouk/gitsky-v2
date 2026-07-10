"""Détection d'intrusion applicative (Chap 14) — logique PURE, sans I/O.

`detect_event` classe une requête suspecte en une des trois catégories, par
sévérité décroissante (injection > scanner > path_scan), ou renvoie None. Cette
pureté rend la détection exhaustivement testable sans middleware ni base.
"""

import re

# Chemins typiques de scan (medium). Comparaison insensible à la casse.
SUSPICIOUS_PATHS: tuple[str, ...] = (
    "/.git",
    "/.env",
    "/.aws",
    "/wp-config.php",
    "/wp-login.php",
    "/admin.php",
    "/phpmyadmin",
    "/.ssh",
)

# User-Agents d'outils offensifs (high).
SCANNER_AGENTS: tuple[str, ...] = (
    "sqlmap",
    "nikto",
    "nmap",
    "nuclei",
    "gobuster",
    "dirbuster",
    "masscan",
)

# Patterns d'injection (critical) : SQLi, XSS, template injection.
_INJECTION_RES: tuple[re.Pattern, ...] = (
    re.compile(r"('|%27)\s*or\s+\d+\s*=\s*\d+", re.IGNORECASE),  # ' OR 1=1
    re.compile(r"\bunion\s+select\b", re.IGNORECASE),
    re.compile(r"<\s*script", re.IGNORECASE),  # XSS
    re.compile(r"\{\{.*?\}\}"),  # template injection {{7*7}}
)


def detect_event(
    path: str, user_agent: str | None = None, query: str | None = None
) -> dict | None:
    # 1. Injection (critical) — le plus grave, testé en premier.
    for pattern in _INJECTION_RES:
        if pattern.search(f"{path}?{query or ''}"):
            return {
                "event_type": "injection_attempt",
                "severity": "critical",
                "details": {"pattern": pattern.pattern},
            }

    # 2. Scanner (high).
    ua = (user_agent or "").lower()
    for tool in SCANNER_AGENTS:
        if tool in ua:
            return {
                "event_type": "scanner_detected",
                "severity": "high",
                "details": {"tool": tool},
            }

    # 3. Path scan (medium).
    lowered = path.lower()
    for suspicious in SUSPICIOUS_PATHS:
        if suspicious in lowered:
            return {
                "event_type": "path_scan",
                "severity": "medium",
                "details": {"matched": suspicious},
            }

    return None
