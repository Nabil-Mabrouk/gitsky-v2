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
