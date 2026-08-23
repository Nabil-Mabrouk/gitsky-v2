"""Skins de la vitrine (Phase 5, incrément 4).

Trois systèmes de design curés (clean / editorial / bold) pilotés par
`landing.skin`. On rend le template Jinja directement (rapide, focalisé sur la
logique de skin, sans génération copier complète).
"""

import re
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

SRC = Path(__file__).resolve().parents[1]
VITRINE = SRC / "generator" / "template" / "vitrine"
sys.path.insert(0, str(SRC / "shared_services"))

from studio.agents import _PALETTES  # noqa: E402
from studio.guardrails import contrast_ratio  # noqa: E402

_env = Environment(loader=FileSystemLoader(str(VITRINE)))
_BRANDING = {
    "primary_color": "#4F46E5",
    "primary_foreground": "#FFFFFF",
    "font_family": "Inter",
    "display_font_family": "Inter",
}


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


def test_each_skin_loads_its_google_font():
    # Bug réel (retour utilisateur, session de refonte design) : le brief
    # choisissait Fraunces/Archivo/Inter par skin depuis toujours, mais rien
    # ne les chargeait jamais nulle part — chaque page retombait
    # silencieusement sur system-ui. Un <link> Google Fonts doit être présent,
    # spécifique au skin rendu.
    assert "fonts.googleapis.com" in _render("clean")
    assert "Fraunces" in _render("editorial")
    assert "Archivo" in _render("bold")


def test_display_font_family_flows_into_css_variable():
    branding = {**_BRANDING, "display_font_family": "Fraunces"}
    html = _env.get_template("landing.html.jinja").render(
        project_name="acme",
        branding=branding,
        landing={"skin": "editorial", "blocks": [{"type": "hero", "headline": "H", "subhead": "S"}]},
    )
    assert '--font-display: "Fraunces"' in html


def test_dark_mode_media_query_present_and_repaints_surfaces():
    for skin in ("clean", "editorial", "bold"):
        html = _render(skin)
        assert "prefers-color-scheme: dark" in html, skin
        # Les surfaces teintées (alternance de section, cartes) doivent
        # mixer vers var(--bg), pas vers "white" en dur — sinon elles
        # resteraient claires même en dark mode (bug réel évité par relecture
        # avant déploiement, pas détecté par un test avant cette regression).
        assert "color-mix(in srgb, var(--primary) 6%, white)" not in html, skin
        assert "color-mix(in srgb, var(--primary) 4%, white)" not in html, skin


def test_primary_ink_passes_contrast_against_dark_bg_for_full_palette():
    # Bug réel trouvé par capture d'écran (pas par un test) : le ratio de mix
    # --primary-ink choisi au départ (68% primaire / 32% blanc) passait pour
    # la plupart des primaires curées mais échouait le contraste WCAG AA
    # (< 4.5) pour les plus sombres : #1A1A1A (~3.27) et #000091 (~3.02 —
    # Bleu France, couleur RÉELLE de politique-ia déjà en ligne). Corrigé à
    # 40%/60%, vérifié numériquement (pire cas 7.36 sur toute la palette).
    # Ce test rejoue le calcul contre --bg réel du template ET la palette
    # réelle d'agents.py, pour qu'un futur ajout de couleur ou changement de
    # ratio ne puisse pas réintroduire la régression silencieusement.
    dark_bg = "#0b0b0c"  # doit matcher --bg sous @media (prefers-color-scheme: dark)
    mix_ratio = 0.40  # doit matcher le pourcentage de --primary-ink dans landing.html.jinja

    def mix_toward_white(hex_color: str, pct: float) -> str:
        h = hex_color.lstrip("#")
        r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
        mixed = tuple(round(c * pct + 255 * (1 - pct)) for c in (r, g, b))
        return "#{:02x}{:02x}{:02x}".format(*mixed)

    candidates = [p["primary"] for p in _PALETTES] + ["#000091"]  # + Bleu France (politique-ia)
    for primary in candidates:
        ink = mix_toward_white(primary, mix_ratio)
        ratio = contrast_ratio(ink, dark_bg)
        assert ratio >= 4.5, (primary, ink, ratio)


def test_no_hardcoded_surface_colors_outside_root_tokens():
    # Garde-fou : toute nouvelle règle qui réintroduirait #111/#eee/#ddd/un
    # blanc en dur serait inatteignable par le dark mode. Les SEULES
    # occurrences légitimes vivent dans les blocs :root (light + dark).
    for skin in ("clean", "editorial", "bold"):
        html = _render(skin)
        style = html.split("<style>", 1)[1].split("</style>", 1)[0]
        # Retire les deux blocs :root (light et dark) avant de vérifier.
        without_roots = re.sub(r":root\s*\{[^}]*\}", "", style)
        for literal in ("#111", "#eee", "#ddd", "background: #fff", "border: 3px solid #111"):
            assert literal not in without_roots, (skin, literal)
