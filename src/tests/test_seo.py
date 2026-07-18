"""SEO core de bout en bout (Chap 10) — sitemap.xml + robots.txt.

Vérifie que le sitemap est bien *dynamique* : il n'expose les URLs d'un module
que lorsque son flag est actif (règle d'isolation Chap 5 §3), ne liste que les
pages publiques, et génère les alternates hreflang quand i18n est actif.

Base SQLite dédiée (fichier temporaire) injectée par override de get_db. Les
flags de module et i18n sont pilotés en mutant le singleton `settings` capturé
par app.core.seo (même instance renvoyée par get_settings, cf. lru_cache).
"""

import asyncio
import atexit
import os
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.models  # noqa: E402,F401  (enregistre User)
import app.core.seo as seo  # noqa: E402
import app.modules.monetization.models  # noqa: E402,F401
import app.modules.tutorials.models  # noqa: E402,F401
from app.core.database import Base, get_db  # noqa: E402
from app.core.models import UserRole  # noqa: E402
from app.modules.monetization.models import Product  # noqa: E402
from app.modules.tutorials.models import Tutorial  # noqa: E402

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_seo_{os.getpid()}.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}")
TestingSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

_SM_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


async def _seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestingSession() as db:
        db.add_all(
            [
                Tutorial(title="Intro", slug="intro", access_role=UserRole.anonymous),
                Tutorial(title="Pro", slug="pro", access_role=UserRole.premium),
                Product(name="Ebook", slug="ebook", price_cents=2900, is_active=True),
                Product(name="Vieux", slug="vieux", price_cents=900, is_active=False),
            ]
        )
        await db.commit()


asyncio.run(_seed())


async def _override_get_db():
    async with TestingSession() as session:
        yield session


app = FastAPI()
app.include_router(seo.router)
app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)


@atexit.register
def _cleanup() -> None:
    asyncio.run(engine.dispose())
    try:
        _DB_FILE.unlink()
    except OSError:
        pass


def _reset_flags() -> None:
    seo.settings.module_tutorials = False
    seo.settings.module_monetization_shop = False
    seo.settings.module_i18n = False
    seo.settings.supported_languages = ["fr"]
    seo.settings.site_url = "https://mon-projet.com"


def _locs(xml: str) -> set[str]:
    root = ET.fromstring(xml)
    return {loc.text for loc in root.findall(".//sm:url/sm:loc", _SM_NS)}


def test_robots_points_to_sitemap_and_blocks_api():
    _reset_flags()
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert "Sitemap: https://mon-projet.com/sitemap.xml" in r.text
    assert "Disallow: /api/" in r.text


def test_sitemap_is_valid_xml_with_home_when_no_modules():
    _reset_flags()
    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")
    assert _locs(r.text) == {"https://mon-projet.com/"}


def test_sitemap_lists_only_public_tutorials_when_enabled():
    _reset_flags()
    seo.settings.module_tutorials = True
    locs = _locs(client.get("/sitemap.xml").text)
    assert "https://mon-projet.com/learn/intro" in locs
    # Le tutorial premium n'est pas indexable.
    assert "https://mon-projet.com/learn/pro" not in locs


def test_sitemap_omits_disabled_module_urls():
    _reset_flags()  # shop désactivé
    seo.settings.module_tutorials = True
    locs = _locs(client.get("/sitemap.xml").text)
    assert not any("/shop/" in loc for loc in locs)


def test_sitemap_lists_only_active_products_when_shop_enabled():
    _reset_flags()
    seo.settings.module_monetization_shop = True
    locs = _locs(client.get("/sitemap.xml").text)
    assert "https://mon-projet.com/shop/ebook" in locs
    assert "https://mon-projet.com/shop/vieux" not in locs


def test_sitemap_emits_hreflang_alternates_when_i18n_active():
    _reset_flags()
    seo.settings.module_tutorials = True
    seo.settings.module_i18n = True
    seo.settings.supported_languages = ["fr", "en"]
    body = client.get("/sitemap.xml").text
    assert 'hreflang="en"' in body
    assert 'hreflang="x-default"' in body
    # La version anglaise de la home apparaît comme URL à part entière.
    assert "https://mon-projet.com/en/" in _locs(body)


def test_no_hreflang_when_single_language_even_if_i18n_flag_on():
    _reset_flags()
    seo.settings.module_i18n = True
    seo.settings.supported_languages = ["fr"]
    body = client.get("/sitemap.xml").text
    assert "hreflang" not in body
