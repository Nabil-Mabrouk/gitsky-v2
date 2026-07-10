"""Guardrails additionnels + traçabilité persistée (Phase 5, incrément 6).

Claims à risque, diversité inter-projets, et persistance immuable des runs.
"""

import sys
import tempfile
from pathlib import Path

import yaml

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC / "shared_services"))

from studio.guardrails import check, check_claims, check_diversity  # noqa: E402
from studio.inputs import HarvestPacket  # noqa: E402
from studio.manifest import Block, Brief, CreativeManifest  # noqa: E402
from studio.pipeline import run, save_run  # noqa: E402


def _manifest(project: str, skin: str, primary: str) -> CreativeManifest:
    return CreativeManifest(
        project=project,
        brief=Brief(skin=skin, palette={"primary": primary, "primary_foreground": "#FFFFFF"}),
        blocks=[Block(type="hero", headline="H", subhead="S"), Block(type="email_capture", cta="Go")],
    )


def test_claims_flagged_and_clean_copy_passes():
    risky = [Block(type="hero", headline="Le meilleur outil, garanti 100%", subhead="x")]
    assert check_claims(risky)
    clean = [Block(type="hero", headline="Collecte tes signaux", subhead="Simple et rapide")]
    assert check_claims(clean) == []


def test_diversity_flags_identical_sibling():
    m = _manifest("proj-b", "clean", "#4F46E5")
    assert check_diversity(m, [_manifest("proj-a", "clean", "#4F46E5")])
    assert check_diversity(m, [_manifest("proj-a", "editorial", "#C8452D")]) == []


def test_check_passes_for_clean_manifest():
    assert check(_manifest("proj", "clean", "#4F46E5")) == []


def test_run_persisted_immutably_and_reloadable():
    result = run(HarvestPacket(project="x", idea_oneliner="Collecte tes signaux"))
    with tempfile.TemporaryDirectory() as tmp:
        path = save_run(result, Path(tmp))
        assert path.exists()
        assert path.name == f"{result.trace.run_id}.yaml"
        data = yaml.safe_load(path.read_text("utf-8"))
        assert data["trace"]["run_id"] == result.trace.run_id
        assert data["manifest"]["project"] == "x"
        assert data["verdict"]["pass"] is True
