"""Scripts de maintenance par projet (Phase 6, incr 5 — Chap 23 parties 1-3).

Ces scripts bash pilotent Docker : on les exerce à travers Git Bash avec un
FAUX `docker` en tête de PATH, plus un faux `mail`/`aws`. On vérifie les
comportements que le Chap 23 exige — dump créé et vérifié, rotation au-delà de
la rétention, chemin corrompu, alerte, codes de sortie — sans démon Docker.

Les scripts eux-mêmes sont statiques (livrés verbatim) ; on les lit depuis le
template, la génération étant déjà couverte par ailleurs.
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

MAINTENANCE_SCRIPTS = [
    "backup_db.sh", "test_restore.sh", "emergency_restore.sh",
    "check_security.sh", "check_disk.sh", "check_errors.sh", "db_health.sql",
]

BASH = shutil.which("bash") or ""
pytestmark = pytest.mark.skipif(not BASH, reason="bash requis (Git Bash)")


def _write_lf(path: Path, content: str) -> None:
    # newline="" : ne pas traduire \n en \r\n (défaut Windows). Bash (Git Bash)
    # laisse fuiter un \r CRLF dans les chaînes echo et les variables sourcées —
    # exactement le genre de bug que ces scripts subiraient sur un checkout CRLF.
    path.write_text(content, encoding="utf-8", newline="")


def _make_fake_bin(dirpath: Path, name: str, body: str) -> None:
    """Crée un exécutable shim `name` dans dirpath (shebang bash)."""
    script = dirpath / name
    _write_lf(script, "#!/usr/bin/env bash\n" + textwrap.dedent(body))
    script.chmod(0o755)


def _run(script: Path, project: Path, fakebin: Path, env_backup: str) -> subprocess.CompletedProcess:
    """Lance un script du projet avec fakebin en tête de PATH."""
    _write_lf(project / ".env.backup", env_backup)
    dst_scripts = project / "scripts"
    dst_scripts.mkdir(exist_ok=True)
    shutil.copy(script, dst_scripts / script.name)

    env = dict(os.environ)
    # fakebin d'abord : notre faux `docker` gagne sur le vrai s'il existe.
    env["PATH"] = str(fakebin) + os.pathsep + env["PATH"]
    return subprocess.run(
        [BASH, str(dst_scripts / script.name)],
        capture_output=True,
        text=True,
        # Les scripts émettent de l'UTF-8 (accents). Sans ceci, subprocess
        # décode en cp1252 sous Windows et « Intégrité » devient du mojibake.
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(project),
    )


# --- backup_db.sh ----------------------------------------------------------


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


def _backup_env(project: Path, **over) -> str:
    base = {
        "POSTGRES_CONTAINER": "pain-scraper_db",
        "POSTGRES_DB": "pain_scraper",
        "POSTGRES_USER": "pain_scraper",
        "BACKUP_DIR": str(project / "backups").replace("\\", "/"),
        "BACKUP_RETENTION": "14",
    }
    base.update(over)
    return "\n".join(f"{k}={v}" for k, v in base.items()) + "\n"


def _fake_docker_ok(fakebin: Path) -> None:
    # inspect -> "running" ; exec ... pg_dump -> un dump SQL bidon sur stdout.
    _make_fake_bin(fakebin, "docker", r"""
        case "$1" in
          inspect) echo "running" ;;
          exec)    echo "-- dump SQL factice"; echo "CREATE TABLE t (id int);" ;;
          *)       ;;
        esac
    """)


def test_backup_creates_verified_gzip(project, fakebin):
    _fake_docker_ok(fakebin)
    r = _run(SCRIPTS / "backup_db.sh", project, fakebin, _backup_env(project))

    assert r.returncode == 0, r.stderr
    dumps = list((project / "backups").glob("backup_pain_scraper_*.sql.gz"))
    assert len(dumps) == 1
    # Le fichier est un gzip valide et contient bien le dump.
    import gzip
    assert b"CREATE TABLE" in gzip.decompress(dumps[0].read_bytes())
    assert "Intégrité OK" in r.stdout


def test_backup_alerts_and_fails_when_container_down(project, fakebin):
    # inspect ne renvoie pas "running" : le conteneur est absent/arrêté.
    _make_fake_bin(fakebin, "docker", 'echo "exited"')
    alert_log = (project / "alert.log").as_posix()
    _make_fake_bin(fakebin, "mail", f'cat >> "{alert_log}"')

    r = _run(SCRIPTS / "backup_db.sh", project, fakebin,
             _backup_env(project, ALERT_EMAIL="ops@mystudio.com"))

    assert r.returncode == 1
    # Aucune sauvegarde ne doit être produite.
    assert list((project / "backups").glob("*.sql.gz")) == []
    # L'alerte a été envoyée (le faux `mail` a reçu le message).
    assert (project / "alert.log").exists()


def test_backup_removes_corrupt_dump(project, fakebin):
    # pg_dump "réussit" mais gzip -t échouera : le pipe injecte des octets non-gzip.
    # On simule en rendant `gzip` inoffensif ? Non : plus simple, docker exec
    # émet du contenu, mais on force la corruption via un faux gzip -t.
    _fake_docker_ok(fakebin)
    # Faux gzip : compresse normalement (-9) mais échoue toujours au test (-t).
    _make_fake_bin(fakebin, "gzip", r"""
        for a in "$@"; do
          if [[ "$a" == "-t" ]]; then exit 1; fi
        done
        exec /usr/bin/gzip "$@"
    """)
    r = _run(SCRIPTS / "backup_db.sh", project, fakebin, _backup_env(project))

    assert r.returncode == 1
    assert "corrompu" in r.stdout
    # Le dump corrompu ne doit pas rester sur le disque.
    assert list((project / "backups").glob("*.sql.gz")) == []


def test_backup_rotation_deletes_beyond_retention(project, fakebin):
    _fake_docker_ok(fakebin)
    backups = project / "backups"
    backups.mkdir()
    # Un vieux dump (20 jours) et un récent (1 jour) ; rétention = 14.
    import time
    old = backups / "backup_pain_scraper_20000101_000000.sql.gz"
    recent = backups / "backup_pain_scraper_20991231_000000.sql.gz"
    for f, age_days in ((old, 20), (recent, 1)):
        f.write_bytes(b"\x1f\x8b\x00")  # entête gzip bidon
        past = time.time() - age_days * 86400
        os.utime(f, (past, past))

    r = _run(SCRIPTS / "backup_db.sh", project, fakebin, _backup_env(project))

    assert r.returncode == 0
    assert not old.exists(), "le dump de 20 jours (> rétention 14) doit être supprimé"
    assert recent.exists(), "le dump récent doit être conservé"


def test_backup_uses_env_backup_names_not_hardcoded(project, fakebin):
    # Régression sur l'écart au livre : les noms viennent de .env.backup, pas
    # d'un `hitl_postgres_1` codé en dur. On capture les args passés à docker.
    arglog = (project / "docker_args.log").as_posix()
    _make_fake_bin(fakebin, "docker", f"""
        echo "$@" >> "{arglog}"
        case "$1" in
          inspect) echo "running" ;;
          exec)    echo "CREATE TABLE t (id int);" ;;
        esac
    """)
    _run(SCRIPTS / "backup_db.sh", project, fakebin,
         _backup_env(project, POSTGRES_CONTAINER="autre-projet_db",
                     POSTGRES_DB="autre_projet"))
    calls = (project / "docker_args.log").read_text(encoding="utf-8")
    assert "autre-projet_db" in calls
    assert "hitl" not in calls


# --- Qualité des scripts livrés --------------------------------------------


@pytest.mark.parametrize("name", [
    "backup_db.sh", "test_restore.sh", "emergency_restore.sh",
    "check_security.sh", "check_disk.sh", "check_errors.sh",
])
def test_scripts_pass_bash_syntax_check(name):
    r = subprocess.run([BASH, "-n", str(SCRIPTS / name)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# --- Livraison dans les projets générés ------------------------------------


def test_scripts_ship_into_generated_projects():
    with projet_genere("pain-scraper", "t1") as dst:
        for name in MAINTENANCE_SCRIPTS:
            assert (dst / "scripts" / name).is_file(), name
        # L'exemple de config est pré-rempli avec les noms RÉELS du projet.
        example = (dst / ".env.backup.example").read_text(encoding="utf-8")
        assert "POSTGRES_CONTAINER=pain-scraper_db" in example
        assert "POSTGRES_DB=pain_scraper" in example
        # Go-template Docker (`{{.State.Status}}`) livré verbatim, pas rendu.
        assert "{{.State.Status}}" in (dst / "scripts" / "backup_db.sh").read_text(
            encoding="utf-8"
        )


def test_t0_env_example_flags_no_database():
    with projet_genere("landing-x", "t0") as dst:
        example = (dst / ".env.backup.example").read_text(encoding="utf-8")
        # T0 n'a pas de base : l'exemple doit le signaler explicitement.
        assert "landing sans base" in example


def test_shipped_scripts_have_unix_line_endings():
    # Les scripts tournent sur Ubuntu (Chap 22) : un CRLF (checkout Windows)
    # casse bash. Le .gitattributes livré doit garantir LF.
    with projet_genere("pain-scraper", "t1") as dst:
        assert (dst / ".gitattributes").is_file()
        for name in MAINTENANCE_SCRIPTS:
            raw = (dst / "scripts" / name).read_bytes()
            assert b"\r" not in raw, f"{name} contient un CRLF (casse bash sur Linux)"


@pytest.mark.parametrize("name", [
    "backup_db.sh", "test_restore.sh", "emergency_restore.sh",
    "check_security.sh", "check_disk.sh", "check_errors.sh",
])
def test_scripts_carry_no_legacy_hitl_names(name):
    # Le Chap 23 code en dur `hitl` partout ; nos scripts doivent être neutres.
    # On regarde le CODE exécuté (hors commentaires) : un commentaire peut citer
    # légitimement `hitl_postgres_1` pour expliquer l'écart au livre.
    code = "\n".join(
        line for line in (SCRIPTS / name).read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "hitl" not in code
    assert "/opt/0-hitl" not in code
