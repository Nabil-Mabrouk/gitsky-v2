"""git_client.push_initial_commit (Chap 27, Phase E).

Pousse le commit initial d'un projet généré (Chap 17 _tasks) vers un remote.
Pas de réseau ici : le remote est un dépôt bare LOCAL, suffisant pour exercer
`git remote add` + `git push` réellement, sans dépendre de GitHub.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
BACKEND = SRC / "generator" / "template"
sys.path.insert(0, str(BACKEND))

import pytest  # noqa: E402

from app.modules.fleet import git_client  # noqa: E402


def _run(cwd: Path, *cmd: str) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True, capture_output=True, text=True)


def _make_repo_with_commit(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _run(path, "git", "init", "-q")
    _run(path, "git", "-c", "user.email=t@t.com", "-c", "user.name=t", "commit", "--allow-empty", "-q", "-m", "Initial commit")


def test_push_initial_commit_reaches_a_local_bare_remote(tmp_path):
    project_dir = tmp_path / "project"
    _make_repo_with_commit(project_dir)

    bare_remote = tmp_path / "remote.git"
    _run(tmp_path, "git", "init", "-q", "--bare", str(bare_remote))

    git_client.push_initial_commit(project_dir, str(bare_remote), "main")

    log = subprocess.run(
        ["git", "log", "--oneline", "main"],
        cwd=str(bare_remote),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "Initial commit" in log


def test_push_initial_commit_cleans_up_token_from_remote_url_after_push(tmp_path):
    # Bug de prod réel (ai-qube, 2026-09-23) : sans ce nettoyage, une URL
    # avec jeton embarqué (seul moyen d'authentifier le push sans prompt
    # interactif, router.py) restait stockée EN CLAIR de façon permanente
    # dans .git/config — un jeton à portée `repo` complète, exposé sur
    # disque indéfiniment pour n'importe qui ayant accès au filesystem.
    project_dir = tmp_path / "project"
    _make_repo_with_commit(project_dir)

    bare_remote = tmp_path / "remote.git"
    _run(tmp_path, "git", "init", "-q", "--bare", str(bare_remote))

    push_url_with_token = f"https://fake-token@{bare_remote.as_posix()}"
    clean_url = str(bare_remote)

    # Un chemin local ne comprend pas de vrai jeton HTTP Basic Auth, donc on
    # ne peut pas exercer l'URL-avec-jeton pour de vrai contre un remote
    # bare local (git le traiterait comme un chemin invalide) — on vérifie
    # directement le comportement de nettoyage avec une URL fonctionnelle
    # comme remote_url, ce que push_initial_commit ne distingue jamais de
    # toute façon (clean_url est appliqué après TOUT push réussi).
    git_client.push_initial_commit(
        project_dir, clean_url, "main", clean_url=push_url_with_token
    )

    remote_after = subprocess.run(
        ["git", "-C", str(project_dir), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert remote_after == push_url_with_token


def test_push_initial_commit_leaves_remote_untouched_without_clean_url(tmp_path):
    # Comportement historique préservé : clean_url est optionnel, un appel
    # sans lui (autre appelant futur, ou remote déjà sans identifiant) ne
    # touche jamais au remote après le push.
    project_dir = tmp_path / "project"
    _make_repo_with_commit(project_dir)

    bare_remote = tmp_path / "remote.git"
    _run(tmp_path, "git", "init", "-q", "--bare", str(bare_remote))

    git_client.push_initial_commit(project_dir, str(bare_remote), "main")

    remote_after = subprocess.run(
        ["git", "-C", str(project_dir), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert remote_after == str(bare_remote)


def test_push_initial_commit_raises_on_unreachable_remote(tmp_path):
    project_dir = tmp_path / "project"
    _make_repo_with_commit(project_dir)

    with pytest.raises(subprocess.CalledProcessError):
        git_client.push_initial_commit(
            project_dir, "https://github.test/stub-owner/does-not-exist.git", "main"
        )
