"""`copier update` + `_migrations` (Phase 2, incrément D).

Prouve le mécanisme central de Copier pour GitSky : propager une évolution du
template aux projets existants. On construit un template versionné par tags git
(v0.9.0 puis v1.0.0), on génère un projet en v0.9.0, on fait évoluer le template
en v1.0.0, puis `copier update` doit exécuter la migration déclarée à la version
1.0.0 (ici SIMULÉE : écrit `.gitsky/updated.json` avec VERSION_FROM/TO).
"""

import json
import os
import shutil
import stat
import subprocess
import sys
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
    # ".git" exclu aussi : GENERATOR est un submodule depuis la scission qui a
    # rendu `copier update` fonctionnel — sans ce filtre, son fichier .git
    # (gitlink vers le gitdir du monorepo parent) se retrouve copié tel quel
    # dans dst, et le `git init` ci-dessous échoue (exit 128) en tombant sur
    # une référence cassée plutôt qu'un dossier vierge.
    shutil.copytree(
        GENERATOR,
        dst,
        ignore=shutil.ignore_patterns(
            "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache",
            "dist", "*.pyc", "*.db", ".git",
        ),
    )
    _git(dst, "init", "-q")
    _git(dst, "config", "core.autocrlf", "false")  # évite un worktree "sale"
    _git(dst, "config", "user.email", "t@t")
    _git(dst, "config", "user.name", "t")
    _git(dst, "add", "-A")
    _git(dst, "commit", "-q", "-m", "v0.9.0")
    _git(dst, "tag", "v0.9.0")


def test_copier_update_runs_migration():
    root = Path(tempfile.mkdtemp())
    try:
        template = root / "template"
        _make_versioned_template(template)

        project = root / "project"
        run_copy(
            str(template),
            str(project),
            data={"project": {"name": "pain-scraper", "tier": "t1"}},
            defaults=True,
            quiet=True,
            unsafe=True,
        )
        # L'answers file rend l'update possible ; la migration n'a pas encore tourné.
        assert (project / ".copier-answers.yml").exists()
        assert not (project / ".gitsky" / "updated.json").exists()

        # Évolution du template franchissant la version 1.0.0 de la migration.
        _git(template, "commit", "--allow-empty", "-q", "-m", "v1.0.0")
        _git(template, "tag", "v1.0.0")

        run_update(
            str(project), defaults=True, overwrite=True, quiet=True, unsafe=True
        )

        # La migration _migrations a RÉELLEMENT tourné (scripts.migrate) pendant l'update.
        upd = json.loads((project / ".gitsky" / "updated.json").read_text("utf-8"))
        assert "1.0.0" in upd["version_to"]
        assert upd["status"] == "applied"
        assert upd["migrate_returncode"] == 0
    finally:
        _rmtree_robuste(root)
