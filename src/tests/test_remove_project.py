"""scripts/remove-project.sh — suppression définitive d'un projet (2026-11-27).

Le vrai docker et le vrai llm-proxy-keys.sh sont remplacés par des faux qui
journalisent leurs appels ; HOME/.ssh et PROJECTS_DIR sont des dossiers de test.
"""

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "shared_services" / "scripts"
BASH = shutil.which("bash") or ""
pytestmark = pytest.mark.skipif(not BASH, reason="bash requis (Git Bash)")

SSH_CONFIG = (
    "Host github.com-other\n  HostName github.com\n  IdentityFile /k/other\n  IdentitiesOnly yes\n"
    "\nHost github.com-politique-ia\n  HostName github.com\n  IdentityFile /k/p\n  IdentitiesOnly yes\n"
    "\nHost github.com-zzz\n  HostName github.com\n  IdentityFile /k/zzz\n  IdentitiesOnly yes\n"
)


def _w(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="")


def _setup(tmp_path: Path, env_local: str = "FOO=1\n") -> dict:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy(SRC / "remove-project.sh", scripts / "remove-project.sh")
    log = tmp_path / "calls.log"
    _w(scripts / "llm-proxy-keys.sh", "#!/usr/bin/env bash\n" + f'echo "llm $@" >> "{log.as_posix()}"\n')
    (scripts / "llm-proxy-keys.sh").chmod(0o755)
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    _w(fakebin / "docker", "#!/usr/bin/env bash\n" + textwrap.dedent(f"""\
        echo "docker $(basename "$PWD") $@" >> "{log.as_posix()}"
        """))
    (fakebin / "docker").chmod(0o755)
    projects = tmp_path / "projects"
    proj = projects / "politique-ia"
    proj.mkdir(parents=True)
    _w(proj / ".env.local", env_local)
    ssh = tmp_path / "ssh"
    ssh.mkdir()
    _w(ssh / "config", SSH_CONFIG)
    _w(ssh / "politique-ia_deploy_key", "k")
    _w(ssh / "politique-ia_deploy_key.pub", "k")
    return {"scripts": scripts, "fakebin": fakebin, "projects": projects, "proj": proj,
            "ssh": ssh, "log": log}


def _run(ctx: dict, *args: str, confirm: str = "politique-ia") -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = str(ctx["fakebin"]) + os.pathsep + env["PATH"]
    env["PROJECTS_DIR"] = ctx["projects"].as_posix()
    env["SSH_DIR"] = ctx["ssh"].as_posix()
    # Octets, pas texte : sous Windows, le mode texte ajouterait un \r à la
    # saisie, ce qu'une frappe au clavier sur le serveur ne fait jamais.
    r = subprocess.run([BASH, (ctx["scripts"] / "remove-project.sh").as_posix(), *args],
                       input=(confirm + "\n").encode(), capture_output=True, env=env)
    return subprocess.CompletedProcess(r.args, r.returncode, r.stdout.decode("utf-8", "replace"),
                                       r.stderr.decode("utf-8", "replace"))


def _calls(ctx: dict) -> list[str]:
    return ctx["log"].read_text(encoding="utf-8").splitlines() if ctx["log"].exists() else []


def test_full_removal_in_order(tmp_path):
    ctx = _setup(tmp_path, "LLM_PROXY_TOKEN=sk-abc\n")
    r = _run(ctx, "politique-ia")
    assert r.returncode == 0, r.stderr
    assert _calls(ctx) == ["llm delete-key politique-ia",
                           "docker politique-ia compose down -v --rmi local"]
    assert not ctx["proj"].exists()
    assert not (ctx["ssh"] / "politique-ia_deploy_key").exists()
    assert not (ctx["ssh"] / "politique-ia_deploy_key.pub").exists()
    config = (ctx["ssh"] / "config").read_text(encoding="utf-8")
    assert "github.com-politique-ia" not in config
    assert "Host github.com-other\n  HostName github.com\n  IdentityFile /k/other" in config
    assert "Host github.com-zzz\n  HostName github.com\n  IdentityFile /k/zzz\n  IdentitiesOnly yes" in config
    assert "sk-abc" not in r.stdout + r.stderr


def test_no_llm_key_skips_revocation(tmp_path):
    ctx = _setup(tmp_path, "FOO=1\nLLM_PROXY_TOKEN=\n")
    r = _run(ctx, "politique-ia")
    assert r.returncode == 0, r.stderr
    assert _calls(ctx) == ["docker politique-ia compose down -v --rmi local"]
    assert not ctx["proj"].exists()


def test_wrong_confirmation_deletes_nothing(tmp_path):
    ctx = _setup(tmp_path, "LLM_PROXY_TOKEN=sk-abc\n")
    r = _run(ctx, "politique-ia", confirm="politique")
    assert r.returncode == 1
    assert _calls(ctx) == []
    assert ctx["proj"].exists()
    assert (ctx["ssh"] / "politique-ia_deploy_key").exists()
    assert "github.com-politique-ia" in (ctx["ssh"] / "config").read_text(encoding="utf-8")


def test_refuses_fleet_dashboard_unknown_project_and_bad_names(tmp_path):
    ctx = _setup(tmp_path)
    (ctx["projects"] / "fleet-dashboard").mkdir()
    assert _run(ctx, "fleet-dashboard", confirm="fleet-dashboard").returncode == 1
    assert (ctx["projects"] / "fleet-dashboard").exists()
    assert _run(ctx, "inconnu", confirm="inconnu").returncode == 1
    assert _run(ctx, "../etc", confirm="../etc").returncode == 2
    assert _run(ctx).returncode == 2
    assert _calls(ctx) == []
