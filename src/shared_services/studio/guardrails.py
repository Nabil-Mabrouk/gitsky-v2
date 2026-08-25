"""Guardrails du Studio (Chap 24) — vérifications DÉTERMINISTES.

a11y (contraste WCAG), structure, claims à risque et diversité inter-projets sont
CALCULÉS (fiables), pas jugés par une IA. Le juge de marque LLM viendra en plus.
"""

import re

# Catalogue de blocs que Landing.tsx sait effectivement rendre (Chap 24 —
# generator/template/frontend/src/pages/Landing.tsx dispatch vers
# components/blocks/*.tsx) — tout type hors de cette liste est
# silencieusement OMIS (pas d'erreur, la section n'apparaît juste pas).
# Le prompt de l'assembleur demande déjà ce catalogue, mais une réponse LLM
# non-stub peut dévier (l'exemple de manifest du Chap 24 utilise lui-même
# `pain_points`, hors catalogue) — ce guardrail rend la contrainte réelle,
# pas seulement suggérée.
_KNOWN_BLOCK_TYPES = {"hero", "features", "email_capture", "testimonial", "faq", "pricing"}

# Champs requis par type, exactement ceux que les composants de
# components/blocks/*.tsx lisent. Trouvé en prod : le premier manifest
# généré par un vrai LLM (pas le stub) utilisait des noms de champs plausibles
# mais différents (item.description au lieu de item.body, block.attribution
# au lieu de block.author, ...) — passait `_KNOWN_BLOCK_TYPES` (bon type) mais
# rendait une section vide (mauvais champs, silencieusement absents du JSX).
# Le prompt de l'assembleur documente maintenant ce contrat, mais rien ne
# garantit qu'un futur appel LLM le respecte — ce guardrail le vérifie.
# Uniquement les champs rendus SANS garde conditionnelle dans le composant —
# leur absence laisse une section visiblement vide/cassée, pas juste moins
# riche. (headline est optionnel partout sauf hero.)
_REQUIRED_FIELDS = {
    "hero": ["headline", "subhead"],
    "features": ["items"],
    "email_capture": ["cta"],
    "testimonial": ["quote", "attribution"],
    "faq": ["items"],
    "pricing": ["plans"],
}
_REQUIRED_ITEM_FIELDS = {
    "features": ("items", ["title", "description"]),
    "faq": ("items", ["question", "answer"]),
}

# Variantes de layout par type (Phase 1 — retour utilisateur : la vitrine
# n'a qu'une seule structure HTML par type de bloc, tout projet du même skin
# se ressemble). `layout` absent = comportement par défaut, rétrocompatible.
_KNOWN_LAYOUTS = {
    "hero": {"centered", "split"},
    "features": {"list", "grid", "alternating"},
    "testimonial": {"quote-block", "card"},
    "faq": {"list", "accordion"},
}

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

    for b in manifest.blocks:
        if b.type not in _KNOWN_BLOCK_TYPES:
            failures.append(
                f"structure: type de bloc « {b.type} » hors catalogue "
                f"(rendu silencieusement omis par le template) — "
                f"catalogue : {sorted(_KNOWN_BLOCK_TYPES)}"
            )
            continue

        data = b.model_dump()
        for field in _REQUIRED_FIELDS.get(b.type, []):
            if not data.get(field):
                failures.append(
                    f"structure: bloc « {b.type} » sans champ « {field} » "
                    f"requis par le template (section rendue vide/incomplète)"
                )

        if b.type in _REQUIRED_ITEM_FIELDS:
            items_key, item_fields = _REQUIRED_ITEM_FIELDS[b.type]
            for i, item in enumerate(data.get(items_key, [])):
                for field in item_fields:
                    if not item.get(field):
                        failures.append(
                            f"structure: bloc « {b.type} » item {i} sans champ "
                            f"« {field} » requis par le template"
                        )

        layout = data.get("layout")
        if layout:
            if b.type in _KNOWN_LAYOUTS:
                if layout not in _KNOWN_LAYOUTS[b.type]:
                    failures.append(
                        f"structure: bloc « {b.type} » layout « {layout} » inconnu "
                        f"(catalogue : {sorted(_KNOWN_LAYOUTS[b.type])})"
                    )
            else:
                failures.append(
                    f"structure: bloc « {b.type} » a un champ « layout » mais ce "
                    f"type n'a pas de variante — champ ignoré par le template"
                )

    failures += check_claims(manifest.blocks)
    if siblings:
        failures += check_diversity(manifest, siblings)

    return failures
