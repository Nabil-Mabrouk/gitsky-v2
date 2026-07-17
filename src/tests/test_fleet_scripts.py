"""Scripts de maintenance à l'échelle de la flotte (Phase 6, incr 6 — Chap 23).

backup-fleet.sh boucle sur les CONTENEURS `*_db` de la flotte (écart au livre :
le Chap 23 énumère `pg_database` d'une instance partagée ; GitSky a un conteneur
par projet). On l'exerce via Git Bash avec un faux `docker` qui simule deux
projets.
"""

import gzip
import os
import shutil
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

SHARED_SCRIPTS = (
    Path(__file__).resolve().parents[1] / "shared_services" / "scripts"
)
FLEET_SCRIPTS = ["backup-fleet.sh", "fleet-disk.sh", "fleet-health.sh"]

BASH = shutil.which("bash") or ""
pytestmark = pytest.mark.skipif(not BASH, reason="bash requis (Git Bash)")


def _write_lf(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="")


def _fake_docker(fakebin: Path, body: str) -> None:
    d = fakebin / "docker"
    _write_lf(d, "#!/usr/bin/env bash\n" + textwrap.dedent(body))
    d.chmod(0o755)


def _run(script_name: str, fakebin: Path, cwd: Path, **env_over) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = str(fakebin) + os.pathsep + env["PATH"]
    env.update(env_over)
    return subprocess.run(
        [BASH, str(SHARED_SCRIPTS / script_name)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, cwd=str(cwd),
    )


# --- backup-fleet.sh -------------------------------------------------------


def _fake_docker_two_projects(fakebin: Path) -> None:
    # `docker ps` liste 2 conteneurs *_db ; `docker exec ... pg_dump` émet du SQL.
    _fake_docker(fakebin, r"""
        case "$1" in
          ps)   echo "pain-scraper_db"; echo "launch-me_db" ;;
          exec) echo "-- dump"; echo "CREATE TABLE t (id int);" ;;
        esac
    """)


def test_fleet_backup_dumps_every_project_container(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    backups = tmp_path / "backups"
    _fake_docker_two_projects(fakebin)

    r = _run("backup-fleet.sh", fakebin, tmp_path,
             BACKUP_DIR=backups.as_posix(), BACKUP_RETENTION="14")

    assert r.returncode == 0, r.stderr
    dumps = sorted(p.name.split("_20")[0] for p in backups.glob("*.dump.gz"))
    # Un dump par projet ; base = nom de projet avec tirets -> underscores.
    assert dumps == ["launch_me", "pain_scraper"]
    # Les dumps sont de vrais gzip contenant le SQL.
    for f in backups.glob("*.dump.gz"):
        assert b"CREATE TABLE" in gzip.decompress(f.read_bytes())


def test_fleet_backup_handles_empty_fleet(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    backups = tmp_path / "backups"
    _fake_docker(fakebin, 'case "$1" in ps) ;; esac')  # aucun conteneur

    r = _run("backup-fleet.sh", fakebin, tmp_path, BACKUP_DIR=backups.as_posix())
    assert r.returncode == 0
    assert "Aucun conteneur" in r.stdout


def test_fleet_backup_rotation_removes_old_dumps(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    backups = tmp_path / "backups"; backups.mkdir()
    _fake_docker_two_projects(fakebin)

    old = backups / "stale_20000101_000000.dump.gz"
    old.write_bytes(b"\x1f\x8b\x00")
    past = time.time() - 20 * 86400  # 20 j > rétention 14
    os.utime(old, (past, past))

    r = _run("backup-fleet.sh", fakebin, tmp_path,
             BACKUP_DIR=backups.as_posix(), BACKUP_RETENTION="14")
    assert r.returncode == 0
    assert not old.exists(), "un dump de 20 j (> rétention) doit être supprimé"


def test_fleet_backup_reports_failed_project(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    backups = tmp_path / "backups"
    # pg_dump échoue (exit 1) pour tout conteneur.
    _fake_docker(fakebin, r"""
        case "$1" in
          ps)   echo "broken_db" ;;
          exec) exit 1 ;;
        esac
    """)
    r = _run("backup-fleet.sh", fakebin, tmp_path, BACKUP_DIR=backups.as_posix())
    assert r.returncode == 1
    # Aucun dump corrompu ne doit rester.
    assert list(backups.glob("*.dump.gz")) == []


def test_fleet_backup_loops_containers_not_pg_database(tmp_path):
    # Écart au livre acté : on énumère via `docker ps` (conteneurs), jamais via
    # `SELECT datname FROM pg_database` d'une instance partagée.
    body = (SHARED_SCRIPTS / "backup-fleet.sh").read_text(encoding="utf-8")
    code = "\n".join(l for l in body.splitlines() if not l.lstrip().startswith("#"))
    assert "docker ps" in code
    assert "pg_database" not in code


# --- Qualité des scripts livrés --------------------------------------------


@pytest.mark.parametrize("name", FLEET_SCRIPTS)
def test_fleet_scripts_pass_bash_syntax(name):
    r = subprocess.run([BASH, "-n", str(SHARED_SCRIPTS / name)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("name", FLEET_SCRIPTS)
def test_fleet_scripts_have_unix_line_endings(name):
    # Exécutés sur l'Ubuntu partagé (Chap 22) : un CRLF casse bash.
    assert b"\r" not in (SHARED_SCRIPTS / name).read_bytes()
