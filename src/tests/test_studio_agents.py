"""Filet déterministe de layout dans l'assembleur (Phase 1 — variantes).

Sans lui, un LLM qui n'émet jamais "layout" (la sortie JSON la plus sûre à
produire) ferait ship toute la fonctionnalité sans aucun effet visible — le
guardrail ne peut détecter qu'une valeur invalide, pas une absence de choix.
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC / "shared_services"))

from studio import agents  # noqa: E402
from studio.guardrails import _KNOWN_LAYOUTS  # noqa: E402
from studio.inputs import HarvestPacket  # noqa: E402
from studio.manifest import Brief  # noqa: E402


def test_assembler_fills_missing_layout_from_known_catalog(monkeypatch):
    monkeypatch.delenv("LLM_PROXY_URL", raising=False)  # force le chemin stub
    packet = HarvestPacket(project="proj-x", idea_oneliner="Une idée")
    brief = Brief(skin="clean", palette={"primary": "#4F46E5", "primary_foreground": "#FFFFFF"})
    copy_blocks = [{"type": "hero", "headline": "H", "subhead": "S"}]

    blocks = agents.assembler(packet, brief, copy_blocks, media_assets=[])

    hero = next(b for b in blocks if b["type"] == "hero")
    assert hero["layout"] in _KNOWN_LAYOUTS["hero"]


def test_fallback_layout_is_deterministic_per_project_and_type():
    a = agents._fallback_layout("proj-x", "features")
    b = agents._fallback_layout("proj-x", "features")
    assert a == b
    assert a in _KNOWN_LAYOUTS["features"]


def test_fallback_layout_does_not_override_explicit_choice(monkeypatch):
    monkeypatch.delenv("LLM_PROXY_URL", raising=False)
    packet = HarvestPacket(project="proj-x", idea_oneliner="Une idée")
    brief = Brief(skin="clean", palette={"primary": "#4F46E5", "primary_foreground": "#FFFFFF"})
    copy_blocks = [{"type": "hero", "headline": "H", "subhead": "S", "layout": "split"}]

    blocks = agents.assembler(packet, brief, copy_blocks, media_assets=[])

    hero = next(b for b in blocks if b["type"] == "hero")
    assert hero["layout"] == "split"


def test_media_populates_hero_asset_ref_via_stub(monkeypatch):
    # Chemin nominal dev/test (LLM_PROXY_URL absent) : image.generate_image
    # retombe sur son propre stub PNG plutôt que de laisser asset_ref vide —
    # exerce tout le pipeline comme le ferait un vrai appel.
    monkeypatch.delenv("LLM_PROXY_URL", raising=False)
    packet = HarvestPacket(project="proj-x", idea_oneliner="Une idée")
    brief = Brief(skin="clean", palette={"primary": "#4F46E5", "primary_foreground": "#FFFFFF"})

    media_assets = agents.media(packet, brief)

    hero = next(m for m in media_assets if m["id"] == "hero")
    assert hero["asset_ref"].startswith("data:image/png;base64,")


def test_media_degrades_silently_when_image_generation_fails(monkeypatch):
    # Une panne transitoire de l'API image (rate-limit, content policy) ne
    # doit PAS faire échouer tout le pipeline — dégradation en absence
    # d'asset_ref, la vitrine reste fonctionnelle sans image (panneau dégradé
    # côté template). Le fail-closed du stub reste testé séparément dans
    # test_failclosed_contract.py — ceci teste la tolérance à une panne
    # RÉSEAU/API, pas l'absence de configuration.
    def _boom(prompt, model="gpt-image-2"):
        raise RuntimeError("panne API image simulée")

    monkeypatch.setattr(agents.image, "generate_image", _boom)
    packet = HarvestPacket(project="proj-x", idea_oneliner="Une idée")
    brief = Brief(skin="clean", palette={"primary": "#4F46E5", "primary_foreground": "#FFFFFF"})

    media_assets = agents.media(packet, brief)

    hero = next(m for m in media_assets if m["id"] == "hero")
    assert "asset_ref" not in hero
