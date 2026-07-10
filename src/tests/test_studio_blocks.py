"""Catalogue de blocs de la vitrine (Phase 5, incrément 2).

Les 6 types de blocs se rendent en HTML valide ; l'email_capture poste vers le
landing-collector (same-origin /leads) ; un bloc inconnu est ignoré sans casser.
"""

import os
import shutil
import stat
import tempfile
from html.parser import HTMLParser
from pathlib import Path

from copier import run_copy

SRC = Path(__file__).resolve().parents[1]
GENERATOR = SRC / "generator"


def _rmtree_robuste(path: Path) -> None:
    def _onexc(func, p, exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    shutil.rmtree(path, onexc=_onexc)


def _generate_landing(landing: dict) -> str:
    root = Path(tempfile.mkdtemp())
    try:
        dst = root / "proj"
        run_copy(
            str(GENERATOR),
            str(dst),
            data={"project": {"name": "acme", "tier": "t0"}, "landing": landing},
            defaults=True,
            quiet=True,
            unsafe=True,
        )
        return (dst / "vitrine" / "landing.html").read_text("utf-8")
    finally:
        _rmtree_robuste(root)


FULL_LANDING = {
    "blocks": [
        {"type": "hero", "headline": "Titre Hero", "subhead": "Sous-titre"},
        {"type": "features", "title": "Fonctions", "items": [{"title": "Rapide", "body": "Très rapide"}]},
        {"type": "testimonial", "quote": "Produit génial", "author": "Alice"},
        {"type": "faq", "title": "FAQ", "items": [{"q": "Comment ?", "a": "Comme ça"}]},
        {"type": "pricing", "title": "Tarifs", "plans": [{"name": "Pro", "price": "29€", "features": ["X", "Y"]}]},
        {"type": "email_capture", "headline": "Rejoignez", "cta": "S'inscrire"},
    ]
}


def test_full_block_catalog_renders_valid_html():
    html = _generate_landing(FULL_LANDING)
    HTMLParser().feed(html)  # parseable sans exception
    for token in [
        "Titre Hero", "Sous-titre",
        "Fonctions", "Rapide", "Très rapide",
        "Produit génial", "Alice",
        "FAQ", "Comment ?", "Comme ça",
        "Tarifs", "Pro", "29€",
        "Rejoignez", "S'inscrire",
    ]:
        assert token in html, token
    # email_capture branché au collector partagé (same-origin).
    assert "/leads" in html
    assert '"acme"' in html  # projet injecté dans le POST JS


def test_unknown_block_is_skipped_gracefully():
    html = _generate_landing(
        {"blocks": [
            {"type": "hero", "headline": "OK", "subhead": "x"},
            {"type": "bloc_inconnu", "foo": "bar"},
        ]}
    )
    HTMLParser().feed(html)
    assert "OK" in html
    assert "bloc_inconnu" not in html
    assert "bar" not in html
