"""Creative Manifest (Phase 5, incrément 3).

Validation + mapping vers données copier + stockage versionné + déterminisme :
deux générations depuis le même manifest produisent une vitrine identique
(donnée `landing-manifest.json` + thème `theme.css` — le rendu HTML lui-même
est React, Chap 24, donc hors scope de ce module Studio pur-Python).
"""

import os
import shutil
import stat
import sys
import tempfile
import time
from pathlib import Path

from copier import run_copy

SRC = Path(__file__).resolve().parents[1]
GENERATOR = SRC / "generator"
sys.path.insert(0, str(SRC / "shared_services"))

from studio.manifest import (  # noqa: E402
    Block,
    Brief,
    CreativeManifest,
    load_manifest,
    save_manifest,
    to_copier_data,
)


def _rmtree_robuste(path: Path) -> None:
    # Sous Windows, un .git contient des objets en lecture seule ET un handle
    # peut rester brièvement ouvert (processus git qui vient de sortir,
    # antivirus). On rend inscriptible, puis on réessaie le retrait complet
    # avec un court backoff tant que le verrou transitoire n'est pas relâché.
    def _onexc(func, p, exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    for essai in range(5):
        try:
            shutil.rmtree(path, onexc=_onexc)
            return
        except (PermissionError, OSError):
            if essai == 4:
                raise
            time.sleep(0.2 * (essai + 1))


def _manifest() -> CreativeManifest:
    return CreativeManifest(
        project="pain-scraper",
        brief=Brief(
            skin="editorial",
            palette={"primary": "#C8452D", "primary_foreground": "#FFFFFF"},
            type_pairing={"display": "Fraunces", "body": "Inter"},
            tone="direct",
            rationale="audience dev, ton technique",
        ),
        blocks=[
            Block(type="hero", headline="Marre du scraping ?", subhead="On collecte."),
            Block(type="email_capture", cta="Rejoindre"),
        ],
    )


def test_to_copier_data_maps_brief_and_blocks():
    data = to_copier_data(_manifest())
    assert data["branding"]["primary_color"] == "#C8452D"
    assert data["branding"]["font_family"] == "Inter"
    blocks = data["landing"]["blocks"]
    assert blocks[0]["type"] == "hero"
    assert blocks[0]["headline"] == "Marre du scraping ?"
    assert blocks[1]["type"] == "email_capture"


def test_save_load_roundtrip_and_autoversion():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        m = _manifest()
        save_manifest(m, base)
        loaded = load_manifest("pain-scraper", base)
        assert loaded.manifest_version == 1
        assert loaded.brief.palette["primary"] == "#C8452D"
        assert loaded.blocks[0].type == "hero"
        # Ré-enregistrement -> version incrémentée (édition = nouvelle version).
        save_manifest(_manifest(), base)
        assert load_manifest("pain-scraper", base).manifest_version == 2


def test_generation_from_manifest_is_deterministic():
    m = _manifest()
    data = {**to_copier_data(m), "project": {"name": "pain-scraper"}}
    root = Path(tempfile.mkdtemp())
    try:
        manifests, themes = [], []
        for i in range(2):
            dst = root / f"proj{i}"
            run_copy(str(GENERATOR), str(dst), data=data, defaults=True, quiet=True, unsafe=True)
            manifests.append((dst / "frontend" / "src" / "landing-manifest.json").read_text("utf-8"))
            themes.append((dst / "frontend" / "src" / "theme.css").read_text("utf-8"))
        # Donnée de landing + thème identiques aux deux générations (reproductibilité).
        assert manifests[0] == manifests[1]
        assert themes[0] == themes[1]
        # Le brief a bien piloté le rendu : contenu dans la donnée de landing,
        # couleur dans le thème (les deux fichiers, plus jamais un seul HTML).
        assert "Marre du scraping ?" in manifests[0]
        assert "#C8452D" in themes[0]
    finally:
        _rmtree_robuste(root)
