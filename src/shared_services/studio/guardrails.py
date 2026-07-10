"""Guardrails du Studio (Chap 24) — vérifications DÉTERMINISTES.

a11y (contraste WCAG) et structure sont calculés, pas jugés par une IA (fiable).
Les guardrails de marque/claims (juge LLM) et la diversité viennent plus tard.
"""


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


def check(manifest) -> list[str]:
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

    return failures
