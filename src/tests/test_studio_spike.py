"""Spike GitSky Studio (Phase 5) — frontière châssis/vitrine + landing data-driven.

S2 : une landing pilotée par un schéma de blocs se rend en HTML valide.
S1 : `copier update` NE réécrit PAS la vitrine éditée à la main (_skip_if_exists).
"""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from html.parser import HTMLParser
from pathlib import Path

from copier import run_copy, run_update

SRC = Path(__file__).resolve().parents[1]
GENERATOR = SRC / "generator"


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


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True
    )


def _make_versioned_template(dst: Path) -> None:
    shutil.copytree(GENERATOR, dst)
    _git(dst, "init", "-q")
    _git(dst, "config", "core.autocrlf", "false")
    _git(dst, "config", "user.email", "t@t")
    _git(dst, "config", "user.name", "t")
    _git(dst, "add", "-A")
    _git(dst, "commit", "-q", "-m", "v0.9.0")
    _git(dst, "tag", "v0.9.0")


# --- S2 : landing data-driven -> HTML valide ------------------------------

def test_landing_renders_blocks_to_valid_html():
    root = Path(tempfile.mkdtemp())
    try:
        dst = root / "proj"
        run_copy(
            str(GENERATOR),
            str(dst),
            data={
                "project": {"name": "pain-scraper", "tier": "t0"},
                "landing": {
                    "blocks": [
                        {"type": "hero", "headline": "Marre du scraping ?", "subhead": "On collecte pour vous."},
                        {"type": "email_capture", "cta": "Je m'inscris"},
                    ]
                },
            },
            defaults=True,
            quiet=True,
            unsafe=True,
        )
        html = (dst / "vitrine" / "landing.html").read_text("utf-8")
        assert html.lstrip().startswith("<!doctype html>")
        assert "Marre du scraping ?" in html  # bloc hero
        assert "Je m'inscris" in html  # bloc email_capture
        HTMLParser().feed(html)  # parseable sans exception
    finally:
        _rmtree_robuste(root)


# --- S1 : la vitrine survit à copier update -------------------------------

def test_vitrine_preserved_on_copier_update():
    root = Path(tempfile.mkdtemp())
    try:
        template = root / "template"
        _make_versioned_template(template)

        project = root / "project"
        run_copy(
            str(template),
            str(project),
            data={"project": {"name": "x", "tier": "t0"}},
            defaults=True,
            quiet=True,
            unsafe=True,
        )
        landing = project / "vitrine" / "landing.html"
        assert landing.exists()

        # Édition humaine de la vitrine, committée (arbre propre pour l'update).
        landing.write_text("<!doctype html><h1>EDITION HUMAINE</h1>", encoding="utf-8")
        _git(project, "config", "core.autocrlf", "false")
        _git(project, "config", "user.email", "t@t")
        _git(project, "config", "user.name", "t")
        _git(project, "add", "-A")
        _git(project, "commit", "-q", "-m", "edit vitrine")

        # Nouvelle version du template qui MODIFIE la vitrine.
        (template / "template" / "vitrine" / "landing.html.jinja").write_text(
            "<!doctype html><h1>NOUVELLE VERSION TEMPLATE</h1>", encoding="utf-8"
        )
        _git(template, "add", "-A")
        _git(template, "commit", "-q", "-m", "v1.0.0")
        _git(template, "tag", "v1.0.0")

        run_update(
            str(project), defaults=True, overwrite=True, quiet=True, unsafe=True
        )

        # _skip_if_exists -> l'édition humaine survit, la version template n'écrase pas.
        content = landing.read_text("utf-8")
        assert "EDITION HUMAINE" in content
        assert "NOUVELLE VERSION TEMPLATE" not in content
    finally:
        _rmtree_robuste(root)
