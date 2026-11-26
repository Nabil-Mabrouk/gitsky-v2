"""scripts/umami-setup.sh init (Chap 18 §8, 2026-11-26).

Crée (idempotent) le rôle + la base postgres "umami" sur le postgres partagé,
et génère dans shared_services/.env les secrets UMAMI_DB_PASSWORD et
UMAMI_APP_SECRET s'ils sont vides — sans jamais réécrire une valeur déjà
posée : changer APP_SECRET déconnecte tout le monde et réinitialise les
identifiants anonymes de visite.
"""

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "shared_services" / "scripts" / "umami-setup.sh"
BASH = shutil.which("bash") or ""
pytestmark = pytest.mark.skipif(not BASH, reason="bash requis (Git Bash)")


def _write_lf(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="")


def _setup(tmp_path: Path, env_content: str) -> dict:
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    shared = tmp_path / "shared"
    shared.mkdir()
    _write_lf(shared / ".env", env_content)
    args_log, stdin_log = tmp_path / "args.log", tmp_path / "stdin.log"
    d = fakebin / "docker"
    _write_lf(d, "#!/usr/bin/env bash\n" + textwrap.dedent(f"""\
        echo "$@" >> "{args_log.as_posix()}"
        cat >> "{stdin_log.as_posix()}"
        exit 0
        """))
    d.chmod(0o755)
    return {"fakebin": fakebin, "shared": shared, "args": args_log, "stdin": stdin_log}


def _run(ctx: dict, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = str(ctx["fakebin"]) + os.pathsep + env["PATH"]
    env["SHARED_DIR"] = str(ctx["shared"])
    return subprocess.run([BASH, str(SCRIPT), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)


def _env(ctx: dict) -> dict:
    out = {}
    for line in (ctx["shared"] / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out[k] = v
    return out


def test_init_generates_both_secrets_and_creates_role_and_db(tmp_path):
    ctx = _setup(tmp_path, "UMAMI_HOST=stats.example.com\nUMAMI_DB_PASSWORD=\nUMAMI_APP_SECRET=\n")
    r = _run(ctx, "init")
    assert r.returncode == 0, r.stderr
    env = _env(ctx)
    for key in ("UMAMI_DB_PASSWORD", "UMAMI_APP_SECRET"):
        assert len(env[key]) >= 32 and all(c in "0123456789abcdef" for c in env[key]), key
    assert env["UMAMI_DB_PASSWORD"] != env["UMAMI_APP_SECRET"]
    sql = ctx["stdin"].read_text(encoding="utf-8")
    assert "CREATE ROLE umami" in sql
    assert "ALTER ROLE umami" in sql
    assert "CREATE DATABASE umami OWNER umami" in sql
    # Mot de passe via stdin (SQL), jamais argv ni sortie.
    assert env["UMAMI_DB_PASSWORD"] in sql
    assert env["UMAMI_DB_PASSWORD"] not in ctx["args"].read_text(encoding="utf-8")
    assert env["UMAMI_DB_PASSWORD"] not in r.stdout + r.stderr
    assert env["UMAMI_APP_SECRET"] not in r.stdout + r.stderr


def test_init_never_rewrites_existing_secrets(tmp_path):
    ctx = _setup(tmp_path, "UMAMI_HOST=s.example.com\nUMAMI_DB_PASSWORD=aaaa1111aaaa1111aaaa1111aaaa1111\n"
                           "UMAMI_APP_SECRET=bbbb2222bbbb2222bbbb2222bbbb2222\n")
    r = _run(ctx, "init")
    assert r.returncode == 0, r.stderr
    env = _env(ctx)
    assert env["UMAMI_DB_PASSWORD"] == "aaaa1111aaaa1111aaaa1111aaaa1111"
    assert env["UMAMI_APP_SECRET"] == "bbbb2222bbbb2222bbbb2222bbbb2222"


def test_init_appends_missing_keys(tmp_path):
    # Serveur existant : son .env ne contient pas encore ces lignes.
    ctx = _setup(tmp_path, "OTHER=1\n")
    r = _run(ctx, "init")
    assert r.returncode == 0, r.stderr
    env = _env(ctx)
    assert env["OTHER"] == "1"
    assert len(env["UMAMI_APP_SECRET"]) >= 32
    assert len(env["UMAMI_DB_PASSWORD"]) >= 32


def test_unknown_command_fails_with_usage(tmp_path):
    ctx = _setup(tmp_path, "")
    r = _run(ctx, "frobnicate")
    assert r.returncode != 0
    assert "Usage" in r.stderr
