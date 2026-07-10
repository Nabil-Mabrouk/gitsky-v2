"""Les agents du pipeline Studio (Chap 24) — chacun en sortie structurée.

Réel via LLM proxy si configuré ; sinon `stub()` déterministe et plausible
(testable sans clé). Le DA compose dans les skins/tokens curés (anti-slop).
"""

import hashlib
import json
from pathlib import Path

from studio import llm
from studio.inputs import HarvestPacket
from studio.manifest import Brief

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

# Skin par verticale/audience (le DA compose DANS ce cadre fermé).
_EDITORIAL = ("editorial", "media", "content", "press", "magazine", "news")
_BOLD = ("consumer", "creative", "fashion", "gaming", "bold", "lifestyle")

# Palettes curées (toutes sombre-sur-blanc -> contraste a11y garanti).
_PALETTES = [
    {"primary": "#4F46E5", "primary_foreground": "#FFFFFF"},
    {"primary": "#0F766E", "primary_foreground": "#FFFFFF"},
    {"primary": "#C8452D", "primary_foreground": "#FFFFFF"},
    {"primary": "#1A1A1A", "primary_foreground": "#FFFFFF"},
]
_TYPE_BY_SKIN = {
    "clean": {"display": "Inter", "body": "Inter"},
    "editorial": {"display": "Fraunces", "body": "Inter"},
    "bold": {"display": "Archivo", "body": "Inter"},
}


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
    return data["media"]


def assembler(packet: HarvestPacket, brief: Brief, copy_blocks: list[dict], media_assets: list[dict]) -> list[dict]:
    def stub() -> dict:
        # Arrangement T0 minimal : le copy tel quel (hero + email_capture).
        return {"blocks": copy_blocks}

    data = llm.generate(
        "claude-sonnet-5",
        _prompt("assembler", brief=brief.model_dump(), copy=copy_blocks, media=media_assets),
        stub,
    )
    return data["blocks"]
