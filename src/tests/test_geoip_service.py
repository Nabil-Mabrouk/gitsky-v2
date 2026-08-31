"""GeoIP service — lookup local via un fixture MaxMind réel (round GeoIP).

GEOIP_DB_PATH doit être posé AVANT l'import du module (lifespan lit la
variable au démarrage) — même contrainte que test_landing_collector.py pour
LANDING_DB_URL. Fixture officielle GeoIP2-City-Test.mmdb (dépôt open-source
maxmind/MaxMind-DB, test-data/) : IPs/valeurs vérifiées directement contre
ce fichier avant d'écrire ces tests, pas mémorisées.
"""

import os
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "shared_services"
sys.path.insert(0, str(SHARED))

os.environ["GEOIP_DB_PATH"] = str(
    Path(__file__).resolve().parent / "fixtures" / "GeoIP2-City-Test.mmdb"
)
# Module Python mis en cache par process : sans ce nettoyage, si
# test_geoip_service_no_db.py (autre GEOIP_DB_PATH) a déjà importé
# geoip_service.main dans le même run pytest, ce fichier-ci hériterait de
# SON _reader déjà ouvert au lieu du sien.
sys.modules.pop("geoip_service.main", None)
sys.modules.pop("geoip_service", None)

from fastapi.testclient import TestClient  # noqa: E402

from geoip_service.main import app  # noqa: E402

# `with` obligatoire : sans lui, Starlette ne déclenche jamais le lifespan
# (donc jamais l'ouverture du Reader) — un TestClient(app) nu suffit pour
# landing_collector (tables créées AVANT via asyncio.run, pas dans un
# lifespan), mais pas ici.
client = TestClient(app)
client.__enter__()


def test_resolve_known_ip_returns_country_and_city():
    r = client.get("/resolve", params={"ip": "81.2.69.142"})
    assert r.status_code == 200
    assert r.json() == {"country_code": "GB", "city": "London"}


def test_resolve_private_ip_fails_open():
    r = client.get("/resolve", params={"ip": "127.0.0.1"})
    assert r.status_code == 200
    assert r.json() == {"country_code": "??", "city": None}


def test_resolve_malformed_ip_fails_open():
    r = client.get("/resolve", params={"ip": "not-an-ip"})
    assert r.status_code == 200
    assert r.json() == {"country_code": "??", "city": None}
