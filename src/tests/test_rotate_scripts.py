"""Scripts de rotation de secrets par projet (Chap 23 §2.2, round sécurisation).

Même patron de test que test_maintenance_scripts.py / test_fleet_scripts.py :
un faux `docker` en tête de PATH, aucun démon Docker requis. Ces scripts
tournent sur l'HÔTE (pas dans le conteneur) — ils ont besoin de `docker
compose`/`docker exec`, contrairement à scripts/migrate.py qui tourne DANS
le conteneur.
"""

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from helpers import projet_genere

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


def _run(script: Path, project: Path, fakebin: Path, **env_over) -> subprocess.CompletedProcess:
    dst_scripts = project / "scripts"
    dst_scripts.mkdir(exist_ok=True)
    shutil.copy(script, dst_scripts / script.name)

    env = dict(os.environ)
    env["PATH"] = str(fakebin) + os.pathsep + env["PATH"]
    # Retries rapides pour les scripts qui sondent /health (comme
    # deploy-on-push.sh) — sans ça un test du chemin d'échec dormirait
    # réellement 30 s.
    env["HEALTH_CHECK_RETRIES"] = "1"
    env["HEALTH_CHECK_DELAY"] = "0"
    env.update(env_over)
    return subprocess.run(
        [BASH, str(dst_scripts / script.name)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, cwd=str(project),
    )


def _fake_docker(fakebin: Path, body: str) -> None:
    _make_fake_bin(fakebin, "docker", body)


def _write_env(project: Path, **kv) -> None:
    _write_lf(project / ".env", "\n".join(f"{k}={v}" for k, v in kv.items()) + "\n")


def _base_env(**over) -> dict:
    base = {
        "PROJECT_NAME": "pain-scraper",
        "POSTGRES_USER": "pain_scraper",
        "POSTGRES_DB": "pain_scraper",
        "POSTGRES_PASSWORD": "old-password-value",
        "SECRET_KEY": "old-secret-key-value",
        "MODULE_FLEET": "false",
    }
    base.update(over)
    return base


# --- rotate_secret_key.sh ---------------------------------------------------


def test_rotate_secret_key_writes_new_value_and_recreates_backend(project, fakebin):
    _write_env(project, **_base_env())
    arglog = (project / "docker_args.log").as_posix()
    _fake_docker(fakebin, f'echo "$@" >> "{arglog}"')

    r = _run(SCRIPTS / "rotate_secret_key.sh", project, fakebin)

    assert r.returncode == 0, r.stderr
    env_after = (project / ".env").read_text(encoding="utf-8")
    lines = [l for l in env_after.splitlines() if l.startswith("SECRET_KEY=")]
    assert len(lines) == 1
    new_key = lines[0].split("=", 1)[1]
    assert new_key != "old-secret-key-value"
    assert len(new_key) == 128  # 64 octets hex
    # Autres lignes de .env préservées.
    assert "PROJECT_NAME=pain-scraper" in env_after
    calls = (project / "docker_args.log").read_text(encoding="utf-8")
    assert "compose up -d --force-recreate backend" in calls


def test_rotate_secret_key_fails_loudly_without_project_name(project, fakebin):
    _write_lf(project / ".env", "SECRET_KEY=x\n")  # PROJECT_NAME manquant
    _fake_docker(fakebin, "exit 0")

    r = _run(SCRIPTS / "rotate_secret_key.sh", project, fakebin)

    assert r.returncode == 1
    assert "PROJECT_NAME" in r.stderr


# --- rotate_postgres_password.sh --------------------------------------------


def _fake_docker_pg_rotate(fakebin: Path, *, probe_ok: bool = True) -> None:
    arglog = (fakebin / "args.log").as_posix()
    _fake_docker(fakebin, rf"""
        echo "$@" >> "{arglog}"
        case "$1" in
          exec)
            case "$*" in
              *psql*) exit 0 ;;
              *) {"exit 0" if probe_ok else "exit 1"} ;;
            esac
            ;;
          compose) exit 0 ;;
        esac
    """)


def test_rotate_postgres_password_alters_role_then_env_then_recreates(project, fakebin):
    _write_env(project, **_base_env())
    _fake_docker_pg_rotate(fakebin, probe_ok=True)

    r = _run(SCRIPTS / "rotate_postgres_password.sh", project, fakebin)

    assert r.returncode == 0, r.stderr
    assert "répond" in r.stdout
    env_after = (project / ".env").read_text(encoding="utf-8")
    lines = [l for l in env_after.splitlines() if l.startswith("POSTGRES_PASSWORD=")]
    assert len(lines) == 1
    new_pw = lines[0].split("=", 1)[1]
    assert new_pw != "old-password-value"
    assert len(new_pw) == 128

    calls = (fakebin / "args.log").read_text(encoding="utf-8")
    assert "pain-scraper_db psql -U pain_scraper -d pain_scraper" in calls
    assert "ALTER USER pain_scraper WITH PASSWORD" in calls
    assert new_pw in calls  # le rôle live reçoit bien LE MÊME mot de passe que .env
    assert "compose up -d --force-recreate backend" in calls


def test_rotate_postgres_password_reports_failure_when_health_never_recovers(project, fakebin):
    _write_env(project, **_base_env())
    _fake_docker_pg_rotate(fakebin, probe_ok=False)

    r = _run(SCRIPTS / "rotate_postgres_password.sh", project, fakebin)

    assert r.returncode == 1
    assert "vérifier manuellement" in r.stderr
    # .env est quand même mis à jour : le rôle live A CHANGÉ, revenir en
    # arrière silencieusement serait pire (désynchronise .env du rôle réel).
    assert "old-password-value" not in (project / ".env").read_text(encoding="utf-8")


def test_rotate_postgres_password_never_invokes_curl_inside_container():
    body = (SCRIPTS / "rotate_postgres_password.sh").read_text(encoding="utf-8")
    code = "\n".join(l for l in body.splitlines() if not l.lstrip().startswith("#"))
    assert "curl" not in code


# --- rotate_fleet_tokens.sh --------------------------------------------------


def test_rotate_fleet_tokens_noop_when_module_fleet_inactive(project, fakebin):
    _write_env(project, **_base_env(MODULE_FLEET="false"))
    _fake_docker(fakebin, "exit 0")

    r = _run(SCRIPTS / "rotate_fleet_tokens.sh", project, fakebin)

    assert r.returncode == 0
    assert "rien à faire" in r.stdout
    assert not (project / ".env.local").exists()


def test_rotate_fleet_tokens_fails_without_env_local(project, fakebin):
    _write_env(project, **_base_env(MODULE_FLEET="true"))
    _fake_docker(fakebin, "exit 0")

    r = _run(SCRIPTS / "rotate_fleet_tokens.sh", project, fakebin)

    assert r.returncode == 1
    assert ".env.local" in r.stderr


def test_rotate_fleet_tokens_rewrites_env_local_and_warns_about_crontab(project, fakebin):
    _write_env(project, **_base_env(MODULE_FLEET="true"))
    _write_lf(
        project / ".env.local",
        "FLEET_REGISTER_TOKEN=old-register-token\n"
        "COLLECTOR_STATS_TOKEN=old-collector-token\n"
        "SMTP_HOST=smtp.gmail.com\n",
    )
    arglog = (project / "docker_args.log").as_posix()
    _fake_docker(fakebin, f'echo "$@" >> "{arglog}"')

    r = _run(SCRIPTS / "rotate_fleet_tokens.sh", project, fakebin)

    assert r.returncode == 0, r.stderr
    env_local = (project / ".env.local").read_text(encoding="utf-8")
    assert "old-register-token" not in env_local
    assert "old-collector-token" not in env_local
    # Ligne non concernée préservée.
    assert "SMTP_HOST=smtp.gmail.com" in env_local
    new_token_line = [l for l in env_local.splitlines() if l.startswith("FLEET_REGISTER_TOKEN=")][0]
    new_token = new_token_line.split("=", 1)[1]
    # Le rappel opérateur affiche la même valeur que celle écrite sur disque.
    assert new_token in r.stdout
    assert "crontab" in r.stdout
    calls = (project / "docker_args.log").read_text(encoding="utf-8")
    assert "compose up -d --force-recreate backend" in calls


# --- Qualité des scripts livrés ---------------------------------------------


@pytest.mark.parametrize("name", [
    "rotate_secret_key.sh", "rotate_postgres_password.sh", "rotate_fleet_tokens.sh",
])
def test_rotate_scripts_pass_bash_syntax_check(name):
    r = subprocess.run([BASH, "-n", str(SCRIPTS / name)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_rotate_scripts_ship_into_generated_projects():
    with projet_genere("pain-scraper") as dst:
        for name in ("rotate_secret_key.sh", "rotate_postgres_password.sh", "rotate_fleet_tokens.sh"):
            assert (dst / "scripts" / name).is_file(), name
