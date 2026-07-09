"""Anonymisation IP + géolocalisation (Chap 13).

`hash_ip` : SHA-256 salé par le secret du projet — conforme RGPD (pas d'IP en
clair, pas de recoupement inter-projets).

`geolocate` : ⚠️ STUB. À CONNECTER au service GeoIP partagé de la flotte
(MaxMind GeoLite2 mutualisé, Chap 18). Voir la dette explicite du plan.
"""

import hashlib


def hash_ip(ip: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{ip}".encode("utf-8")).hexdigest()


def geolocate(ip: str) -> dict:
    # SIMULÉ : retourne un pays inconnu. Le vrai service résout ip -> pays/ville.
    return {"country_code": "??", "city": None}
