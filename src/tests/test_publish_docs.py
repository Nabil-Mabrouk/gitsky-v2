"""scripts/publish-docs.sh (guide d'exploitation, 2026-11-27).

Publie docs/exploitation/*.md dans l'onglet Apprentissage du fleet dashboard :
copie dans le conteneur backend, seed du module tutorials en accès admin,
nettoyage. Le vrai docker est remplacé par un faux qui journalise ses appels.
"""

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "src" / "shared_services" / "scripts" / "publish-docs.sh"
DOCS = ROOT / "docs" / "exploitation"
BASH = shutil.which("bash") or ""
pytestmark = pytest.mark.skipif(not BASH, reason="bash requis (Git Bash)")


def _fake_docker(tmp_path: Path) -> tuple[Path, Path]:
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    log = tmp_path / "docker.log"
    d = fakebin / "docker"
    d.write_text("#!/usr/bin/env bash\n" + textwrap.dedent(f"""\
        echo "$@" >> "{log.as_posix()}"
        exit 0
        """), encoding="utf-8", newline="")
    d.chmod(0o755)
    return fakebin, log


def _run(tmp_path: Path, docs_dir: Path, *args: str):
    fakebin, log = _fake_docker(tmp_path)
    env = dict(os.environ)
    env["PATH"] = str(fakebin) + os.pathsep + env["PATH"]
    env["DOCS_DIR"] = docs_dir.as_posix()
    r = subprocess.run([BASH, str(SCRIPT), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return r, calls


def test_copies_then_seeds_as_admin_then_cleans_up(tmp_path):
    # Nettoyage en root (-u 0) : docker cp dépose les fichiers en root, alors
    # que le backend tourne en non-root — bug vu au premier vrai lancement.
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "01-a.md").write_text("# A\n", encoding="utf-8")
    r, calls = _run(tmp_path, docs)
    assert r.returncode == 0, r.stderr
    assert calls[0] == "exec -u 0 fleet-dashboard_backend rm -rf /tmp/gitsky-exploitation"
    assert calls[1].startswith("cp ") and calls[1].endswith(
        "fleet-dashboard_backend:/tmp/gitsky-exploitation")
    seed = calls[2]
    assert "python -m scripts.seed_tutorials" in seed
    assert "--slug exploiter-gitsky" in seed
    assert "--access-role admin" in seed
    assert seed.endswith("/tmp/gitsky-exploitation")
    assert calls[3] == "exec -u 0 fleet-dashboard_backend rm -rf /tmp/gitsky-exploitation"


def test_refuses_an_empty_docs_dir_without_touching_docker(tmp_path):
    empty = tmp_path / "vide"
    empty.mkdir()
    r, calls = _run(tmp_path, empty)
    assert r.returncode == 1
    assert "aucun fichier .md" in r.stderr
    assert calls == []


def test_rejects_arguments(tmp_path):
    r, calls = _run(tmp_path, DOCS, "inattendu")
    assert r.returncode == 2
    assert "Usage" in r.stderr
    assert calls == []


def test_real_guide_pages_have_a_title_line():
    # seed_tutorials prend la 1re ligne `# Titre` comme titre de la page.
    pages = sorted(DOCS.glob("*.md"))
    assert len(pages) >= 6
    for page in pages:
        first = page.read_text(encoding="utf-8").splitlines()[0]
        assert first.startswith("# "), page.name
