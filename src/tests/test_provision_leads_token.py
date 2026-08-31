"""scripts/provision_leads_token.sh (round leads).

Même patron de test que test_rotate_scripts.py : un faux `docker` en tête de
PATH, aucun démon Docker requis. Formule HMAC-SHA256(COLLECTOR_STATS_TOKEN,
PROJECT_NAME) verrouillée ici ET dans test_collector_stats_token.py
(landing_collector) — les deux DOIVENT produire le même résultat.
"""

import hashlib
import hmac
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

TEMPLATE = Path(__file__).resolve().parents[1] / "generator" / "template"
SCRIPTS = TEMPLATE / "scripts"

BASH = shutil.which("bash") or ""
pytestmark = pytest.mark.skipif(not BASH, reason="bash requis (Git Bash)")


def _write_lf(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="")


def _make_fake_bin(dirpath: Path, name: str, body: str) -> None:
    script = dirpath / name
    _write_lf(script, "#!/usr/bin/env bash\n" + textwrap.dedent(body))
    script.chmod(0o755)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    p = tmp_path / "proj"
    (p / "scripts").mkdir(parents=True)
    return p


@pytest.fixture
def fakebin(tmp_path: Path) -> Path:
    d = tmp_path / "fakebin"
    d.mkdir()
    return d


def _run(project: Path, fakebin: Path, **env_over) -> subprocess.CompletedProcess:
    dst_scripts = project / "scripts"
    dst_scripts.mkdir(exist_ok=True)
    shutil.copy(SCRIPTS / "provision_leads_token.sh", dst_scripts / "provision_leads_token.sh")

    env = dict(os.environ)
    env["PATH"] = str(fakebin) + os.pathsep + env["PATH"]
    env.update(env_over)
    return subprocess.run(
        [BASH, str(dst_scripts / "provision_leads_token.sh")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, cwd=str(project),
    )


def _fake_docker(fakebin: Path, body: str) -> None:
    _make_fake_bin(fakebin, "docker", body)


def _write_env(project: Path, **kv) -> None:
    _write_lf(project / ".env", "\n".join(f"{k}={v}" for k, v in kv.items()) + "\n")


def _derived(master: str, project: str) -> str:
    return hmac.new(master.encode(), project.encode(), hashlib.sha256).hexdigest()


def test_noop_when_module_leads_inactive(project, fakebin):
    _write_env(project, PROJECT_NAME="pain-scraper", MODULE_LEADS="false")
    _fake_docker(fakebin, "exit 0")

    r = _run(project, fakebin, COLLECTOR_STATS_TOKEN="master-token")

    assert r.returncode == 0
    assert "rien à faire" in r.stdout
    assert not (project / ".env.local").exists()


def test_fails_loudly_without_collector_stats_token(project, fakebin):
    _write_env(project, PROJECT_NAME="pain-scraper", MODULE_LEADS="true")
    _fake_docker(fakebin, "exit 0")

    dst_scripts = project / "scripts"
    dst_scripts.mkdir(exist_ok=True)
    shutil.copy(SCRIPTS / "provision_leads_token.sh", dst_scripts / "provision_leads_token.sh")

    env = dict(os.environ)
    env.pop("COLLECTOR_STATS_TOKEN", None)
    env["PATH"] = str(fakebin) + os.pathsep + env["PATH"]
    r = subprocess.run(
        [BASH, str(dst_scripts / "provision_leads_token.sh")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, cwd=str(project),
    )

    assert r.returncode == 1
    assert "COLLECTOR_STATS_TOKEN" in r.stderr


def test_writes_derived_token_and_recreates_backend(project, fakebin):
    _write_env(project, PROJECT_NAME="pain-scraper", MODULE_LEADS="true")
    arglog = (project / "docker_args.log").as_posix()
    _fake_docker(fakebin, f'echo "$@" >> "{arglog}"')

    r = _run(project, fakebin, COLLECTOR_STATS_TOKEN="master-token")

    assert r.returncode == 0, r.stderr
    env_local = (project / ".env.local").read_text(encoding="utf-8")
    lines = [l for l in env_local.splitlines() if l.startswith("LEADS_COLLECTOR_TOKEN=")]
    assert len(lines) == 1
    written = lines[0].split("=", 1)[1]
    assert written == _derived("master-token", "pain-scraper")

    calls = (project / "docker_args.log").read_text(encoding="utf-8")
    assert "compose up -d --force-recreate backend" in calls


def test_rewrites_existing_token_without_duplicating(project, fakebin):
    _write_env(project, PROJECT_NAME="pain-scraper", MODULE_LEADS="true")
    _write_lf(
        project / ".env.local",
        "LEADS_COLLECTOR_TOKEN=stale-value\nSOME_OTHER_VAR=kept\n",
    )
    _fake_docker(fakebin, "exit 0")

    r = _run(project, fakebin, COLLECTOR_STATS_TOKEN="master-token")

    assert r.returncode == 0, r.stderr
    env_local = (project / ".env.local").read_text(encoding="utf-8")
    lines = [l for l in env_local.splitlines() if l.startswith("LEADS_COLLECTOR_TOKEN=")]
    assert len(lines) == 1
    assert lines[0].split("=", 1)[1] == _derived("master-token", "pain-scraper")
    assert "SOME_OTHER_VAR=kept" in env_local


def test_provision_leads_token_passes_bash_syntax_check():
    r = subprocess.run(
        [BASH, "-n", str(SCRIPTS / "provision_leads_token.sh")],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr


def test_provision_leads_token_ships_into_generated_projects():
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from helpers import projet_genere

    with projet_genere("pain-scraper") as dst:
        assert (dst / "scripts" / "provision_leads_token.sh").is_file()
