"""Anonymisation IP + géolocalisation (Chap 13/18).

`hash_ip` : SHA-256 salé par le secret du projet (RGPD, pas d'IP en clair).

`geolocate` : interroge le service GeoIP partagé (MaxMind GeoLite2 mutualisé,
Chap 18) via GEOIP_URL. Sans configuration ou en cas d'échec, retombe proprement
sur un pays inconnu — la géoloc ne doit jamais casser le tracking.
"""

import hashlib
import os

import httpx


def hash_ip(ip: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{ip}".encode("utf-8")).hexdigest()


def geolocate(ip: str, client: httpx.Client | None = None) -> dict:
    url = os.environ.get("GEOIP_URL", "")
    if not url:
        return {"country_code": "??", "city": None}
    try:
        http = client or httpx.Client(timeout=2)
        response = http.get(f"{url.rstrip('/')}/resolve", params={"ip": ip})
        response.raise_for_status()
        data = response.json()
        return {"country_code": data.get("country_code", "??"), "city": data.get("city")}
    except Exception:
        return {"country_code": "??", "city": None}
