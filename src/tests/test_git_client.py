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


def test_push_initial_commit_raises_on_unreachable_remote(tmp_path):
    project_dir = tmp_path / "project"
    _make_repo_with_commit(project_dir)

    with pytest.raises(subprocess.CalledProcessError):
        git_client.push_initial_commit(
            project_dir, "https://github.test/stub-owner/does-not-exist.git", "main"
        )
