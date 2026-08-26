"""Spike GitSky Studio (Phase 5) — frontière châssis/vitrine + landing data-driven.

S2 : une landing pilotée par un schéma de blocs se sérialise en JSON valide
(landing-manifest.json.jinja — le rendu HTML lui-même est React, Chap 24).
S1 : `copier update` NE réécrit PAS la donnée de landing figée à la génération
(_skip_if_exists) — seule la donnée est protégée, pas le code React qui la lit.
"""

import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
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
    # Copie fidèle à un CHECKOUT GIT du template : node_modules, __pycache__ et
    # les caches locaux sont gitignorés dans le vrai dépôt et n'existeraient
    # jamais dans un template versionné. Les embarquer rendait le `git add -A`
    # ci-dessous flaky sous Windows (~40 000 fichiers : antivirus, chemins
    # longs) et n'apportait rien au scénario testé.
    # ".git" exclu : GENERATOR est un submodule depuis la scission qui a rendu
    # `copier update` fonctionnel — sans ce filtre, son fichier .git (gitlink
    # vers le gitdir du monorepo parent) se retrouve copié tel quel dans dst,
    # et le `git init` ci-dessous échoue (exit 128) sur une référence cassée
    # plutôt qu'un dossier vierge.
    shutil.copytree(
        GENERATOR,
        dst,
        ignore=shutil.ignore_patterns(
            "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache",
            "dist", "*.pyc", "*.db", ".git",
        ),
    )
    _git(dst, "init", "-q")
    _git(dst, "config", "core.autocrlf", "false")
    _git(dst, "config", "user.email", "t@t")
    _git(dst, "config", "user.name", "t")
    _git(dst, "add", "-A")
    _git(dst, "commit", "-q", "-m", "v0.9.0")
    _git(dst, "tag", "v0.9.0")


# --- S2 : landing data-driven -> JSON valide, consommé par React ---------

def test_landing_manifest_serializes_blocks_to_valid_json():
    root = Path(tempfile.mkdtemp())
    try:
        dst = root / "proj"
        run_copy(
            str(GENERATOR),
            str(dst),
            data={
                "project": {"name": "pain-scraper"},
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
        manifest = json.loads(
            (dst / "frontend" / "src" / "landing-manifest.json").read_text("utf-8")
        )
        assert manifest["project"] == "pain-scraper"
        assert manifest["blocks"][0]["headline"] == "Marre du scraping ?"
        assert manifest["blocks"][1]["cta"] == "Je m'inscris"
    finally:
        _rmtree_robuste(root)


# --- S1 : la donnée de landing survit à copier update ---------------------

def test_landing_manifest_preserved_on_copier_update():
    root = Path(tempfile.mkdtemp())
    try:
        template = root / "template"
        _make_versioned_template(template)

        project = root / "project"
        run_copy(
            str(template),
            str(project),
            data={"project": {"name": "x"}},
            defaults=True,
            quiet=True,
            unsafe=True,
        )
        manifest_path = project / "frontend" / "src" / "landing-manifest.json"
        assert manifest_path.exists()

        # Édition humaine de la donnée figée, committée (arbre propre pour l'update).
        manifest_path.write_text('{"note": "EDITION HUMAINE"}', encoding="utf-8")
        _git(project, "config", "core.autocrlf", "false")
        _git(project, "config", "user.email", "t@t")
        _git(project, "config", "user.name", "t")
        _git(project, "add", "-A")
        _git(project, "commit", "-q", "-m", "edit landing-manifest")

        # Nouvelle version du template qui MODIFIE le rendu de la donnée.
        (template / "template" / "frontend" / "src" / "landing-manifest.json.jinja").write_text(
            '{"note": "NOUVELLE VERSION TEMPLATE"}', encoding="utf-8"
        )
        _git(template, "add", "-A")
        _git(template, "commit", "-q", "-m", "v1.0.0")
        _git(template, "tag", "v1.0.0")

        run_update(
            str(project), defaults=True, overwrite=True, quiet=True, unsafe=True
        )

        # _skip_if_exists -> l'édition humaine survit, la version template n'écrase pas.
        content = manifest_path.read_text("utf-8")
        assert "EDITION HUMAINE" in content
        assert "NOUVELLE VERSION TEMPLATE" not in content
    finally:
        _rmtree_robuste(root)
