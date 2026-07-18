"""SEO core (Chap 10) — `sitemap.xml` et `robots.txt` générés dynamiquement.

Le SEO fait partie du **core** GitSky : présent à tous les tiers (Chap 2), il
n'a donc pas de flag `MODULE_*` et son routeur est monté inconditionnellement
dans `main.py`.

Le sitemap ne parcourt que les tables des modules **activés**. Comme pour le
chargement conditionnel des routeurs (règle Chap 5 §3), l'import des modèles
d'un module se fait **à l'intérieur du `if settings.module_*`** : un module
désactivé n'introduit ni ses URLs ni ses dépendances dans le flux XML.

Note d'implémentation vs. l'extrait du livre : notre stack SQLAlchemy est
asynchrone (`await db.execute(select(...))` plutôt que `db.query(...)`), et le
critère « indexable » s'appuie sur les champs réellement présents dans les
modèles — `access_role == anonymous` pour un tutorial (pages publiques), et
`is_active` pour un produit.
"""

from __future__ import annotations

from dataclasses import dataclass
from xml.sax.saxutils import escape, quoteattr

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db

router = APIRouter()
settings = get_settings()

_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_XHTML_NS = "http://www.w3.org/1999/xhtml"


@dataclass
class SeoUrl:
    """Une URL indexable : chemin relatif + date de dernière modif optionnelle."""

    path: str
    lastmod: str | None = None


def _abs(path: str) -> str:
    """Transforme un chemin relatif en URL absolue sur l'origine publique."""
    return settings.site_url.rstrip("/") + path


def _localize(path: str, lang: str) -> str:
    """Chemin d'une page dans une langue donnée (la langue par défaut = sans préfixe)."""
    default = settings.supported_languages[0] if settings.supported_languages else "fr"
    return path if lang == default else f"/{lang}{path}"


def _i18n_active() -> bool:
    return bool(settings.module_i18n) and len(settings.supported_languages) > 1


def _static_urls() -> list[SeoUrl]:
    """URLs statiques toujours indexables (page d'accueil publique)."""
    return [SeoUrl(path="/")]


def _render_sitemap(urls: list[SeoUrl]) -> str:
    i18n = _i18n_active()
    langs = settings.supported_languages if i18n else [None]

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    if i18n:
        lines.append(f'<urlset xmlns="{_SITEMAP_NS}" xmlns:xhtml="{_XHTML_NS}">')
    else:
        lines.append(f'<urlset xmlns="{_SITEMAP_NS}">')

    for url in urls:
        # Sans i18n : une entrée par URL. Avec i18n : une entrée par (URL, langue),
        # chacune listant l'ensemble des alternates hreflang (pattern Google).
        for lang in langs:
            loc = _abs(_localize(url.path, lang)) if lang else _abs(url.path)
            lines.append("  <url>")
            lines.append(f"    <loc>{escape(loc)}</loc>")
            if url.lastmod:
                lines.append(f"    <lastmod>{escape(url.lastmod)}</lastmod>")
            if i18n:
                for alt in settings.supported_languages:
                    href = quoteattr(_abs(_localize(url.path, alt)))
                    lines.append(
                        f'    <xhtml:link rel="alternate" hreflang="{alt}" href={href}/>'
                    )
                x_default = quoteattr(_abs(url.path))
                lines.append(
                    f'    <xhtml:link rel="alternate" hreflang="x-default" '
                    f'href={x_default}/>'
                )
            lines.append("  </url>")

    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


@router.get("/sitemap.xml")
async def sitemap(db: AsyncSession = Depends(get_db)) -> Response:
    urls = _static_urls()

    if settings.module_tutorials:
        from app.core.models import UserRole
        from app.modules.tutorials.models import Tutorial

        rows = (
            await db.execute(
                select(Tutorial).where(Tutorial.access_role == UserRole.anonymous)
            )
        ).scalars().all()
        urls += [SeoUrl(path=f"/learn/{t.slug}") for t in rows]

    if settings.module_monetization_shop:
        from app.modules.monetization.models import Product

        rows = (
            await db.execute(select(Product).where(Product.is_active.is_(True)))
        ).scalars().all()
        urls += [SeoUrl(path=f"/shop/{p.slug}") for p in rows]

    return Response(content=_render_sitemap(urls), media_type="application/xml")


@router.get("/robots.txt")
async def robots() -> Response:
    # Autorise l'exploration du contenu public, bloque l'API et les surfaces
    # privées (login, admin) — cohérent avec le noindex des pages non publiques
    # côté frontend (Chap 10 §Indexation sélective).
    body = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /api/",
            "Disallow: /login",
            "Disallow: /admin",
            f"Sitemap: {_abs('/sitemap.xml')}",
            "",
        ]
    )
    return Response(content=body, media_type="text/plain")
