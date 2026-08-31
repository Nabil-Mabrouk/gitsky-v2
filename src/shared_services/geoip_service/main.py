"""API du service GeoIP partagé (Chap 13/18).

Lookup local (aucun appel réseau sortant) dans la base MaxMind GeoLite2-City
(.mmdb), rafraîchie mensuellement par le service one-shot geoipupdate (cron
hôte -> scripts/update-geoip-db.sh) dans le volume partagé geoip_data. Ce
service n'a jamais besoin d'egress-net — seul geoipupdate en a besoin,
volontairement séparé (même raisonnement que llm-proxy vs postgres/
landing-collector : egress-net réservé à ce qui appelle réellement
Internet).

GET /resolve?ip=... -> {"country_code": "XX", "city": "..."} — miroir exact
du contrat déjà figé côté client dans
app/modules/analytics/geoip.py:geolocate() du générateur (jamais modifié
ici, cf. test_geolocate_uses_shared_service_when_configured).

Fail-open côté service, symétrique du fail-open client : une IP privée/
réservée (AddressNotFoundError), une IP malformée (ValueError), ou une base
absente/pas encore téléchargée (premier déploiement, avant le premier run de
update-geoip-db.sh) renvoient toutes {"country_code": "??", "city": None}
en 200 — jamais un 500. La géoloc ne doit jamais faire échouer le tracking
appelant.
"""

import logging
import os
from contextlib import asynccontextmanager

import geoip2.database
import geoip2.errors
from fastapi import FastAPI, Query

logger = logging.getLogger(__name__)

# Chemin par défaut EXACT écrit par l'image officielle maxmindinc/geoipupdate
# (DatabaseDirectory par défaut, jamais surchargé — cf. shared_services/
# docker-compose.yml, service geoipupdate) : ne PAS inventer un autre chemin.
DB_PATH = os.environ.get("GEOIP_DB_PATH", "/usr/share/GeoIP/GeoLite2-City.mmdb")

_reader: geoip2.database.Reader | None = None
_FALLBACK = {"country_code": "??", "city": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _reader
    if os.path.exists(DB_PATH):
        _reader = geoip2.database.Reader(DB_PATH)
        logger.info("Base GeoIP chargée depuis %s", DB_PATH)
    else:
        # Premier déploiement : le volume geoip_data est vide tant que
        # update-geoip-db.sh (geoipupdate) n'a pas tourné une première fois.
        # Ne JAMAIS crash-looper pour ça — /resolve répond "??" jusque-là.
        logger.warning(
            "Base GeoIP absente (%s) — /resolve renverra '??' jusqu'au "
            "premier run de update-geoip-db.sh.",
            DB_PATH,
        )
    yield
    if _reader is not None:
        _reader.close()


app = FastAPI(title="GeoIP Service", lifespan=lifespan)


@app.get("/resolve")
async def resolve(ip: str = Query(...)) -> dict:
    if _reader is None:
        return _FALLBACK
    try:
        response = _reader.city(ip)
    except geoip2.errors.AddressNotFoundError:
        # Cas NORMAL et fréquent : IP privée/réservée/loopback (trafic de
        # dev, health checks internes, proxys sans X-Forwarded-For) — pas
        # une erreur, juste un pays inconnu. Pas de log ici (bruit attendu).
        return _FALLBACK
    except (ValueError, geoip2.errors.GeoIP2Error):
        logger.warning("IP invalide ou échec de lookup GeoIP pour %r", ip)
        return _FALLBACK
    return {
        "country_code": response.country.iso_code or "??",
        "city": response.city.name,
    }
