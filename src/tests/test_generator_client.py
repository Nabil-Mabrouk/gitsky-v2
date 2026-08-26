"""generator_client.py — assemblage du payload copier + génération réelle
(Chap 27, Phase E).

Contrairement à test_generator_spike.py (skip_tasks=True, pour rester rapide
et déterministe sur des dizaines d'appels), ce fichier exerce le chemin RÉEL
utilisé par le wizard de création : `_tasks` s'exécutent, donc le projet
généré a un vrai dépôt git avec un premier commit (Chap 26 §premier push).
"""

import shutil
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
BACKEND = SRC / "generator" / "template"
GENERATOR = SRC / "generator"
sys.path.insert(0, str(BACKEND))

import pytest  # noqa: E402

from app.modules.fleet import generator_client  # noqa: E402


def test_is_valid_project_name():
    assert generator_client.is_valid_project_name("pain-scraper")
    assert generator_client.is_valid_project_name("a")
    assert generator_client.is_valid_project_name("a1-b2")
    assert not generator_client.is_valid_project_name("")
    assert not generator_client.is_valid_project_name("Pain-Scraper")  # majuscules
    assert not generator_client.is_valid_project_name("-leading-hyphen")
    assert not generator_client.is_valid_project_name("trailing-hyphen-")
    assert not generator_client.is_valid_project_name("has_underscore")
    assert not generator_client.is_valid_project_name("has space")


def test_build_config_drops_unknown_module_keys_and_sets_domain_workers():
    config = generator_client.build_config(
        "pain-scraper",
        {"admin": True, "analytics": False, "not_a_real_module": True},
        domain="pain-scraper.com",
        workers=4,
    )
    # Seules les clés connues et effectivement fournies passent — le reste du
    # catalogue (absent d'`overrides`) reste résolu à False par le context
    # hook du générateur (extensions/context.py), pas ici.
    assert config == {
        "project": {"name": "pain-scraper", "domain": "pain-scraper.com", "workers": 4},
        "modules": {"admin": True, "analytics": False},
    }


def test_build_config_omits_domain_and_workers_when_not_provided():
    config = generator_client.build_config("pain-scraper", {})
    assert config["project"] == {"name": "pain-scraper"}


def test_generate_project_raises_when_generator_not_configured(monkeypatch):
    monkeypatch.delenv("GITSKY_GENERATOR_PATH", raising=False)
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(generator_client.GeneratorNotConfigured):
            generator_client.generate_project("p", {"project": {"name": "p"}}, Path(tmp))


def test_generate_project_raises_when_path_has_no_copier_yml(monkeypatch, tmp_path):
    empty = tmp_path / "not-a-generator"
    empty.mkdir()
    monkeypatch.setenv("GITSKY_GENERATOR_PATH", str(empty))
    with pytest.raises(generator_client.GeneratorNotConfigured):
        generator_client.generate_project("p", {"project": {"name": "p"}}, tmp_path / "dest")


def test_generate_project_materializes_a_real_git_repo(monkeypatch):
    monkeypatch.setenv("GITSKY_GENERATOR_PATH", str(GENERATOR))
    monkeypatch.delenv("POSTGRES_CONTAINER", raising=False)
    monkeypatch.delenv("FLEET_URL", raising=False)

    tmp = Path(tempfile.mkdtemp())
    try:
        config = generator_client.build_config("wizard-project", {"admin": True})
        dest = generator_client.generate_project("wizard-project", config, tmp)

        assert dest == tmp / "wizard-project"
        assert (dest / ".git").is_dir()
        assert (dest / "app" / "core" / "config.py").exists()

        # _tasks (Chap 17) : git init/add/commit réels — c'est ce qui rend le
        # projet prêt pour git_client.push_initial_commit.
        log = _run(dest, ["git", "log", "--oneline"])
        assert "Initial commit" in log
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run(cwd: Path, cmd: list[str]) -> str:
    import subprocess

    result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=True)
    return result.stdout
