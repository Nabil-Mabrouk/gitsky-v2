"""Les agents du pipeline Studio (Chap 24) — chacun en sortie structurée.

Réel via LLM proxy si configuré ; sinon `stub()` déterministe et plausible
(testable sans clé). Le DA compose dans les skins/tokens curés (anti-slop).
"""

import hashlib
import json
from pathlib import Path

from studio import image, llm
from studio.inputs import HarvestPacket
from studio.manifest import Brief

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

# Skin par verticale/audience (le DA compose DANS ce cadre fermé).
_EDITORIAL = ("editorial", "media", "content", "press", "magazine", "news")
_BOLD = ("consumer", "creative", "fashion", "gaming", "bold", "lifestyle")

# Palettes curées (toutes sombre-sur-blanc -> contraste a11y garanti par
# guardrails.py::contrast_ratio, >= 4.5 WCAG AA). Élargi de 4 à 10 (retour
# utilisateur : avec seulement 3 skins x 4 primaires = 12 combinaisons, le
# guardrail check_diversity se déclenchait de plus en plus souvent à mesure
# que la flotte grandit — plus de variété réduit directement ce risque).
_PALETTES = [
    {"primary": "#4F46E5", "primary_foreground": "#FFFFFF"},  # indigo
    {"primary": "#0F766E", "primary_foreground": "#FFFFFF"},  # teal
    {"primary": "#C8452D", "primary_foreground": "#FFFFFF"},  # terracotta
    {"primary": "#1A1A1A", "primary_foreground": "#FFFFFF"},  # noir quasi-pur
    {"primary": "#1D4ED8", "primary_foreground": "#FFFFFF"},  # bleu
    {"primary": "#166534", "primary_foreground": "#FFFFFF"},  # vert forêt
    {"primary": "#6D28D9", "primary_foreground": "#FFFFFF"},  # violet
    {"primary": "#9D174D", "primary_foreground": "#FFFFFF"},  # magenta profond
    {"primary": "#78350F", "primary_foreground": "#FFFFFF"},  # ambre/brun
    {"primary": "#334155", "primary_foreground": "#FFFFFF"},  # ardoise
]
_TYPE_BY_SKIN = {
    "clean": {"display": "Inter", "body": "Inter"},
    "editorial": {"display": "Fraunces", "body": "Inter"},
    "bold": {"display": "Archivo", "body": "Inter"},
}

# Variantes de layout par type de bloc (Phase 1 design). Doit rester en
# phase avec _KNOWN_LAYOUTS dans guardrails.py.
_LAYOUT_OPTIONS = {
    "hero": ["centered", "split"],
    "features": ["list", "grid", "alternating"],
    "testimonial": ["quote-block", "card"],
    "faq": ["list", "accordion"],
}


def _fallback_layout(project: str, block_type: str) -> str:
    options = _LAYOUT_OPTIONS[block_type]
    idx = int(hashlib.sha256(f"{project}:{block_type}".encode()).hexdigest(), 16) % len(options)
    return options[idx]


def _prompt(name: str, **ctx) -> str:
    tmpl = (_PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    return f"{tmpl}\n\nCONTEXTE:\n{json.dumps(ctx, ensure_ascii=False, default=str)}"


def _pick_skin(packet: HarvestPacket) -> str:
    text = f"{packet.vertical} {packet.audience}".lower()
    if any(k in text for k in _EDITORIAL):
        return "editorial"
    if any(k in text for k in _BOLD):
        return "bold"
    return "clean"


def _pick_palette(packet: HarvestPacket) -> dict:
    idx = int(hashlib.sha256(packet.project.encode()).hexdigest(), 16) % len(_PALETTES)
    return _PALETTES[idx]


def art_director(packet: HarvestPacket) -> Brief:
    def stub() -> dict:
        skin = _pick_skin(packet)
        return {
            "skin": skin,
            "palette": _pick_palette(packet),
            "type_pairing": _TYPE_BY_SKIN[skin],
            "tone": f"adapté à {packet.audience or 'une audience générale'}",
            "rationale": f"skin '{skin}' pour la verticale '{packet.vertical or 'n/a'}'",
        }

    data = llm.generate("claude-opus-4-8", _prompt("art_director", packet=packet.model_dump()), stub)
    return Brief(**data)


def copywriter(packet: HarvestPacket, brief: Brief) -> list[dict]:
    def stub() -> dict:
        return {
            "blocks": [
                {"type": "hero", "headline": packet.idea_oneliner, "subhead": f"Pour {packet.audience or 'vous'}."},
                {"type": "email_capture", "cta": "Rejoindre la liste"},
            ]
        }

    data = llm.generate(
        "claude-sonnet-5",
        _prompt("copywriter", packet=packet.model_dump(), brief=brief.model_dump()),
        stub,
    )
    return data["blocks"]


def media(packet: HarvestPacket, brief: Brief) -> list[dict]:
    def stub() -> dict:
        return {
            "media": [
                {
                    "id": "hero",
                    "kind": "image",
                    "prompt": f"hero {brief.skin} pour {packet.idea_oneliner}",
                    "license": "generated-owned",
                }
            ]
        }

    data = llm.generate("claude-sonnet-5", _prompt("media", brief=brief.model_dump()), stub)
    media_assets = data["media"]
    # Round B : une seule image générée pour de vrai (le hero) — garde le
    # coût et le scope bornés pour cette première intégration réelle (pas
    # un appel par item de features). Un échec DALL-E (rate-limit, content
    # policy, timeout) ne doit PAS faire échouer tout le pipeline —
    # dégradation silencieuse (pas d'asset_ref), la vitrine reste
    # fonctionnelle sans image (panneau dégradé en repli côté template).
    # Le fail-closed reste entier dans image.py lui-même (jamais de stub
    # silencieux en prod) : c'est une fiabilité TRANSITOIRE de l'API tierce
    # qui est tolérée ici, pas un risque de sécurité comme la fraude
    # webhook Stripe — ne pas généraliser ce pattern sans y repenser.
    for asset in media_assets:
        if asset.get("id") == "hero" and asset.get("kind", "image") == "image":
            try:
                asset["asset_ref"] = image.generate_image(asset["prompt"])
            except RuntimeError:
                pass
    return media_assets


def assembler(packet: HarvestPacket, brief: Brief, copy_blocks: list[dict], media_assets: list[dict]) -> list[dict]:
    def stub() -> dict:
        # Arrangement T0 minimal : le copy tel quel (hero + email_capture).
        return {"blocks": copy_blocks}

    data = llm.generate(
        "claude-sonnet-5",
        _prompt("assembler", brief=brief.model_dump(), copy=copy_blocks, media=media_assets),
        stub,
    )
    blocks = data["blocks"]
    # Filet déterministe (même pattern que _pick_palette) : si le LLM n'émet
    # jamais "layout" (la sortie JSON "la plus sûre" à produire), la variété
    # de layout ne doit pas dépendre uniquement de sa bonne volonté — sinon
    # cette fonctionnalité entière peut ship sans aucun effet visible.
    for b in blocks:
        if b.get("type") in _LAYOUT_OPTIONS and not b.get("layout"):
            b["layout"] = _fallback_layout(packet.project, b["type"])
    return blocks
