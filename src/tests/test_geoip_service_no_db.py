"""GeoIP service — base absente (premier déploiement, round GeoIP).

Fichier séparé de test_geoip_service.py : GEOIP_DB_PATH doit être posé
AVANT l'import du module, donc les deux scénarios (base présente/absente)
ne peuvent pas partager le même process d'import.
"""

import os
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "shared_services"
sys.path.insert(0, str(SHARED))

os.environ["GEOIP_DB_PATH"] = "/nonexistent/GeoLite2-City.mmdb"
# Voir le commentaire identique dans test_geoip_service.py : nettoyage
# nécessaire pour ne pas hériter du module (et de son _reader déjà ouvert)
# importé par l'autre fichier de test dans le même run pytest.
sys.modules.pop("geoip_service.main", None)
sys.modules.pop("geoip_service", None)

from fastapi.testclient import TestClient  # noqa: E402

from geoip_service.main import app  # noqa: E402

client = TestClient(app)
client.__enter__()


def test_resolve_never_crashes_when_database_is_missing():
    # Volume geoip_data vide (avant le premier run de update-geoip-db.sh) —
    # jamais un crash-loop, /resolve répond "??" jusque-là.
    r = client.get("/resolve", params={"ip": "81.2.69.142"})
    assert r.status_code == 200
    assert r.json() == {"country_code": "??", "city": None}
