"""Skins de la vitrine (Chap 24 — landing React).

Trois systèmes de design curés (clean / editorial / bold) pilotés par
`landing.skin`. Depuis que T0 rend la landing via React (plus de gabarit HTML
Jinja par skin), `landing.css` contient TOUJOURS les trois skins — le
scoping se fait au runtime via l'attribut `data-skin` posé par Landing.tsx
(`[data-skin="..."]`), pas au rendu template. On lit donc directement ce
fichier statique plutôt que de rendre un template par skin.

Le chargement de la police Google par skin (Fraunces/Archivo/Inter) et le
repli "skin inconnu -> clean" sont désormais une logique React
(`FONT_HREF_BY_SKIN` dans Landing.tsx) — testés côté frontend
(pages/Landing.test.tsx), pas ici.
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
LANDING_CSS = SRC / "generator" / "template" / "frontend" / "src" / "landing.css"
sys.path.insert(0, str(SRC / "shared_services"))

from studio.agents import _PALETTES  # noqa: E402
from studio.guardrails import contrast_ratio  # noqa: E402

_CSS = LANDING_CSS.read_text("utf-8")


def test_three_skins_have_distinct_css_blocks():
    editorial = [line for line in _CSS.splitlines() if '[data-skin="editorial"]' in line]
    bold = [line for line in _CSS.splitlines() if '[data-skin="bold"]' in line]
    assert editorial and bold
    # "clean" est la base non conditionnelle (.landing, sans attribut) : elle
    # existe forcément (tout le fichier hors [data-skin=...] la porte).
    assert any("[data-skin=" not in line and ".landing" in line for line in _CSS.splitlines())

    assert "Georgia" in "\n".join(editorial)
    assert "uppercase" in "\n".join(bold)


def test_dark_mode_media_query_present_and_repaints_surfaces():
    assert "prefers-color-scheme: dark" in _CSS
    # Les surfaces teintées (alternance de section, cartes) doivent mixer vers
    # var(--bg), pas vers "white" en dur — sinon elles resteraient claires
    # même en dark mode (bug réel évité par relecture avant déploiement, pas
    # détecté par un test avant cette regression).
    assert "color-mix(in srgb, var(--color-primary) 6%, white)" not in _CSS
    assert "color-mix(in srgb, var(--color-primary) 4%, white)" not in _CSS


def test_primary_ink_passes_contrast_against_dark_bg_for_full_palette():
    # Bug réel trouvé par capture d'écran (pas par un test) : le ratio de mix
    # --primary-ink choisi au départ (68% primaire / 32% blanc) passait pour
    # la plupart des primaires curées mais échouait le contraste WCAG AA
    # (< 4.5) pour les plus sombres : #1A1A1A (~3.27) et #000091 (~3.02 —
    # Bleu France, couleur RÉELLE de politique-ia déjà en ligne). Corrigé à
    # 40%/60%, vérifié numériquement (pire cas 7.36 sur toute la palette).
    # Ce test rejoue le calcul contre --bg réel du CSS ET la palette réelle
    # d'agents.py, pour qu'un futur ajout de couleur ou changement de ratio ne
    # puisse pas réintroduire la régression silencieusement.
    dark_bg = "#0b0b0c"  # doit matcher --bg sous @media (prefers-color-scheme: dark)
    mix_ratio = 0.40  # doit matcher le pourcentage de --primary-ink dans landing.css
    assert "--bg: #0b0b0c;" in _CSS
    assert "color-mix(in srgb, var(--color-primary) 40%, white)" in _CSS

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
    import re

    without_roots = re.sub(r":root\s*\{[^}]*\}", "", _CSS)
    for literal in ("#111", "#eee", "#ddd", "background: #fff", "border: 3px solid #111"):
        assert literal not in without_roots, literal
