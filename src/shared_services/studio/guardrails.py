"""Guardrails du Studio (Chap 24) — vérifications DÉTERMINISTES.

a11y (contraste WCAG), structure, claims à risque et diversité inter-projets sont
CALCULÉS (fiables), pas jugés par une IA. Le juge de marque LLM viendra en plus.
"""

import re

# Allégations absolues à risque (floor déterministe ; le nuancé = juge LLM).
_BANNED_CLAIM_RES = [
    re.compile(r"\bn[°o]\s*1\b", re.IGNORECASE),
    re.compile(r"\bnum[ée]ro\s*1\b", re.IGNORECASE),
    re.compile(r"\ble meilleur\b", re.IGNORECASE),
    re.compile(r"\bgaranti\b", re.IGNORECASE),
    re.compile(r"\b100\s*%\b"),
]


def _srgb_to_linear(channel: int) -> float:
    c = channel / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return (
        0.2126 * _srgb_to_linear(r)
        + 0.7152 * _srgb_to_linear(g)
        + 0.0722 * _srgb_to_linear(b)
    )


def contrast_ratio(c1: str, c2: str) -> float:
    l1, l2 = _luminance(c1), _luminance(c2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def check_claims(blocks) -> list[str]:
    failures: list[str] = []
    for block in blocks:
        text = " ".join(
            str(v) for v in block.model_dump().values() if isinstance(v, str)
        )
        for rx in _BANNED_CLAIM_RES:
            if rx.search(text):
                failures.append(f"claims: allégation à risque « {rx.pattern} »")
                break
    return failures


def check_diversity(manifest, siblings) -> list[str]:
    """Flag si un projet frère a exactement le même (skin, couleur primaire)."""
    key = (manifest.brief.skin, manifest.brief.palette.get("primary"))
    for sib in siblings:
        if sib.project == manifest.project:
            continue
        if (sib.brief.skin, sib.brief.palette.get("primary")) == key:
            return [f"diversity: identique (skin+palette) au projet frère '{sib.project}'"]
    return []


def check(manifest, siblings=None) -> list[str]:
    """Renvoie la liste des échecs de guardrail (vide = pass)."""
    failures: list[str] = []

    palette = manifest.brief.palette
    if "primary" in palette and "primary_foreground" in palette:
        if contrast_ratio(palette["primary"], palette["primary_foreground"]) < 4.5:
            failures.append("a11y: contraste primary/foreground < 4.5 (WCAG AA)")

    if not any(b.type == "hero" for b in manifest.blocks):
        failures.append("structure: aucun bloc hero")
    if not any(b.type == "email_capture" for b in manifest.blocks):
        failures.append("structure: aucun bloc de capture d'email (T0)")

    failures += check_claims(manifest.blocks)
    if siblings:
        failures += check_diversity(manifest, siblings)

    return failures
