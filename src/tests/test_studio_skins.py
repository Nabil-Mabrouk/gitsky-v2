"""Skins de la vitrine (Phase 5, incrément 4).

Trois systèmes de design curés (clean / editorial / bold) pilotés par
`landing.skin`. On rend le template Jinja directement (rapide, focalisé sur la
logique de skin, sans génération copier complète).
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

SRC = Path(__file__).resolve().parents[1]
VITRINE = SRC / "generator" / "template" / "vitrine"

_env = Environment(loader=FileSystemLoader(str(VITRINE)))
_BRANDING = {"primary_color": "#4F46E5", "primary_foreground": "#FFFFFF", "font_family": "Inter"}


def _render(skin: str) -> str:
    return _env.get_template("landing.html.jinja").render(
        project_name="acme",
        branding=_BRANDING,
        landing={"skin": skin, "blocks": [{"type": "hero", "headline": "H", "subhead": "S"}]},
    )


def test_three_skins_render_distinct_css():
    clean = _render("clean")
    editorial = _render("editorial")
    bold = _render("bold")

    assert "skin: clean" in clean
    assert "skin: editorial" in editorial and "Georgia" in editorial
    assert "skin: bold" in bold and "uppercase" in bold

    # Trois esthétiques réellement distinctes.
    assert clean != editorial
    assert editorial != bold
    assert bold != clean


def test_unknown_skin_falls_back_to_clean():
    assert "skin: clean" in _render("skin_inexistant")
