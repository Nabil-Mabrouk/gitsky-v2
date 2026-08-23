"""Catalogue de blocs de la vitrine (Phase 5, incrément 2).

Les 6 types de blocs se rendent en HTML valide ; l'email_capture poste vers le
landing-collector (same-origin /leads) ; un bloc inconnu est ignoré sans casser.
"""

import os
import shutil
import stat
import tempfile
import time
from html.parser import HTMLParser
from pathlib import Path

from copier import run_copy

SRC = Path(__file__).resolve().parents[1]
GENERATOR = SRC / "generator"


def _rmtree_robuste(path: Path) -> None:
    # Sous Windows, un .git contient des objets en lecture seule ET un handle
    # peut rester brièvement ouvert (processus git qui vient de sortir,
    # antivirus). On rend inscriptible, puis on réessaie le retrait complet
    # avec un court backoff tant que le verrou transitoire n'est pas relâché.
    def _onexc(func, p, exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    for essai in range(5):
        try:
            shutil.rmtree(path, onexc=_onexc)
            return
        except (PermissionError, OSError):
            if essai == 4:
                raise
            time.sleep(0.2 * (essai + 1))


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


# Champs alignés sur le contrat réellement documenté au prompt de l'assembleur
# (studio/prompts/assembler.md) et lu par landing.html.jinja — PAS sur une
# convention inventée pour le test. Le premier run réel (LLM non-stub, projet
# politique-ia) a produit exactement ces noms (headline/description/
# attribution/question/answer), différents de ce que ce fixture affirmait
# avant correction (title/body/author/q/a) : le test validait un contrat que
# ni le prompt ni le template ne respectaient, la section "features"/"faq"
# de la vitrine réelle rendait vide malgré un test vert.
FULL_LANDING = {
    "blocks": [
        {
            "type": "hero",
            "headline": "Titre Hero",
            "subhead": "Sous-titre",
            "badge": "Nouveau",
            "cta_primary": {"label": "Voir plus", "target": "#features"},
        },
        {
            "type": "features",
            "headline": "Fonctions",
            "items": [{"title": "Rapide", "description": "Très rapide"}],
        },
        {"type": "testimonial", "quote": "Produit génial", "attribution": "Alice"},
        {
            "type": "faq",
            "headline": "FAQ",
            "items": [{"question": "Comment ?", "answer": "Comme ça"}],
        },
        {"type": "pricing", "headline": "Tarifs", "plans": [{"name": "Pro", "price": "29€", "features": ["X", "Y"]}]},
        {
            "type": "email_capture",
            "headline": "Rejoignez",
            "subhead": "Un email, rien d'autre",
            "cta": "S'inscrire",
            "legal_note": "Désinscription en un clic",
        },
    ]
}


def test_full_block_catalog_renders_valid_html():
    html = _generate_landing(FULL_LANDING)
    HTMLParser().feed(html)  # parseable sans exception
    for token in [
        "Titre Hero", "Sous-titre", "Nouveau", "Voir plus",
        "Fonctions", "Rapide", "Très rapide",
        "Produit génial", "Alice",
        "FAQ", "Comment ?", "Comme ça",
        "Tarifs", "Pro", "29€",
        "Rejoignez", "Un email, rien d'autre", "S'inscrire", "Désinscription en un clic",
    ]:
        assert token in html, token
    # email_capture branché au collector partagé (same-origin).
    assert "/leads" in html
    assert '"acme"' in html  # projet injecté dans le POST JS


def test_no_layout_field_keeps_default_markup():
    # Rétrocompatibilité : FULL_LANDING n'a aucun champ "layout" (comme tout
    # manifest généré avant l'introduction des variantes) — le rendu par
    # défaut ne doit porter AUCUN marqueur des nouvelles variantes. Les noms
    # de classe des variantes existent TOUJOURS dans les règles CSS de
    # <style> (statiques, indépendantes du contenu) — ne chercher que dans le
    # <body>, où seule leur UTILISATION réelle apparaîtrait.
    html = _generate_landing(FULL_LANDING)
    body = html.split("</style>", 1)[1]
    for marker in ["hero--split", "feature-grid", "feature-alt", "testimonial-card", "faq-accordion"]:
        assert marker not in body, marker


def test_hero_split_layout_renders_panel():
    html = _generate_landing(
        {"blocks": [
            {"type": "hero", "layout": "split", "headline": "H", "subhead": "S"},
            {"type": "email_capture", "cta": "Go"},
        ]}
    )
    HTMLParser().feed(html)
    assert "hero--split" in html
    assert "hero-panel" in html


def test_features_grid_layout_renders_cards():
    html = _generate_landing(
        {"blocks": [
            {"type": "hero", "headline": "H", "subhead": "S"},
            {"type": "features", "layout": "grid", "headline": "F", "items": [{"title": "A", "description": "B"}]},
            {"type": "email_capture", "cta": "Go"},
        ]}
    )
    HTMLParser().feed(html)
    assert "feature-grid" in html
    assert "feature-card" in html
    assert "A" in html and "B" in html


def test_features_alternating_layout_renders():
    html = _generate_landing(
        {"blocks": [
            {"type": "hero", "headline": "H", "subhead": "S"},
            {"type": "features", "layout": "alternating", "headline": "F", "items": [{"title": "A", "description": "B"}]},
            {"type": "email_capture", "cta": "Go"},
        ]}
    )
    HTMLParser().feed(html)
    assert "feature-alt" in html


def test_testimonial_card_layout_renders():
    html = _generate_landing(
        {"blocks": [
            {"type": "hero", "headline": "H", "subhead": "S"},
            {"type": "testimonial", "layout": "card", "quote": "Q", "attribution": "Alice"},
            {"type": "email_capture", "cta": "Go"},
        ]}
    )
    HTMLParser().feed(html)
    assert "testimonial-card" in html


def test_faq_accordion_layout_renders_details():
    html = _generate_landing(
        {"blocks": [
            {"type": "hero", "headline": "H", "subhead": "S"},
            {"type": "faq", "layout": "accordion", "headline": "FAQ", "items": [{"question": "Q?", "answer": "A."}]},
            {"type": "email_capture", "cta": "Go"},
        ]}
    )
    HTMLParser().feed(html)
    assert "<details>" in html
    assert "<summary>Q?</summary>" in html


def test_hero_image_renders_as_img_in_split_layout():
    html = _generate_landing(
        {
            "hero_image": "data:image/png;base64,AAAA",
            "blocks": [
                {"type": "hero", "layout": "split", "headline": "H", "subhead": "S"},
                {"type": "email_capture", "cta": "Go"},
            ],
        }
    )
    HTMLParser().feed(html)
    assert '<img class="hero-panel" src="data:image/png;base64,AAAA"' in html
    # Le panneau dégradé (repli) ne doit plus apparaître quand une image réelle existe.
    assert '<div class="hero-panel" aria-hidden="true"></div>' not in html


def test_hero_image_renders_as_banner_in_centered_layout():
    html = _generate_landing(
        {
            "hero_image": "data:image/png;base64,AAAA",
            "blocks": [
                {"type": "hero", "headline": "H", "subhead": "S"},
                {"type": "email_capture", "cta": "Go"},
            ],
        }
    )
    HTMLParser().feed(html)
    assert '<img class="hero-image" src="data:image/png;base64,AAAA"' in html


def test_no_hero_image_keeps_gradient_fallback():
    # Rétrocompatibilité : sans hero_image (comme tout manifest antérieur au
    # Round B), le panneau dégradé existant reste inchangé.
    html = _generate_landing(
        {"blocks": [{"type": "hero", "layout": "split", "headline": "H", "subhead": "S"}]}
    )
    HTMLParser().feed(html)
    assert '<div class="hero-panel" aria-hidden="true"></div>' in html
    # Cherche un <img> RENDU (dans <body>), pas une mention dans un
    # commentaire CSS ("donc <div> ET <img> partagent...") — d'où le split.
    body = html.split("</style>", 1)[1]
    assert "<img" not in body


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
