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
FLEET_SCRIPTS = [
    "backup-fleet.sh",
    "fleet-disk.sh",
    "fleet-health.sh",
    "test-restore-fleet.sh",
    "deploy-on-push.sh",
    "lifecycle-fleet.sh",
]

BASH = shutil.which("bash") or ""
pytestmark = pytest.mark.skipif(not BASH, reason="bash requis (Git Bash)")


def _write_lf(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="")


def _fake_docker(fakebin: Path, body: str) -> None:
    d = fakebin / "docker"
    _write_lf(d, "#!/usr/bin/env bash\n" + textwrap.dedent(body))
    d.chmod(0o755)


def _fake_curl(fakebin: Path, log: Path, *, fail: bool = False) -> None:
    # Capture les args réels (dont le payload -d) pour vérifier ce qui est
    # posté à /api/fleet/maintenance/report, sans jamais toucher au réseau.
    c = fakebin / "curl"
    _write_lf(
        c,
        "#!/usr/bin/env bash\n"
        f'echo "$@" >> "{log.as_posix()}"\n'
        + ("exit 1\n" if fail else "exit 0\n"),
    )
    c.chmod(0o755)


def _run(script_name: str, fakebin: Path, cwd: Path, **env_over) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = str(fakebin) + os.pathsep + env["PATH"]
    # deploy-on-push.sh retente sa sonde /health (HEALTH_CHECK_RETRIES fois,
    # HEALTH_CHECK_DELAY s d'écart) — sans ça un test sur le chemin d'échec
    # dormirait réellement 30 s. Sans effet sur les autres scripts (lus,
    # jamais consultés). Un test qui veut vérifier une vraie retentative
    # peut toujours surcharger ces clés via env_over.
    env["HEALTH_CHECK_RETRIES"] = "1"
    env["HEALTH_CHECK_DELAY"] = "0"
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


def test_fleet_backup_uses_project_db_user_not_postgres(tmp_path):
    # Regression : le rôle "postgres" n'existe QUE si POSTGRES_USER vaut
    # littéralement "postgres" (image officielle) — chaque projet GitSky
    # définit POSTGRES_USER = POSTGRES_DB = db_name (.env.jinja), jamais
    # "postgres". `-U postgres` en dur échouait ("role does not exist")
    # contre un vrai conteneur ; invisible ici tant que le mock docker ne
    # loggue/valide aucun credential — d'où ce test qui capture les args réels.
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    backups = tmp_path / "backups"
    log = tmp_path / "docker_calls.log"
    _fake_docker(fakebin, rf"""
        echo "$@" >> "{log.as_posix()}"
        case "$1" in
          ps)   echo "pain-scraper_db" ;;
          exec) echo "-- dump" ;;
        esac
    """)

    r = _run("backup-fleet.sh", fakebin, tmp_path, BACKUP_DIR=backups.as_posix())
    assert r.returncode == 0, r.stderr

    exec_calls = [line for line in log.read_text().splitlines() if line.startswith("exec ")]
    assert exec_calls, "aucun appel docker exec observé"
    for call in exec_calls:
        assert "-U pain_scraper" in call, call
        assert "-U postgres" not in call, call


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


def test_fleet_backup_reports_success_to_maintenance_endpoint(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    backups = tmp_path / "backups"
    log = tmp_path / "curl_calls.log"
    _fake_docker_two_projects(fakebin)
    _fake_curl(fakebin, log)

    r = _run("backup-fleet.sh", fakebin, tmp_path, BACKUP_DIR=backups.as_posix(),
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok")

    assert r.returncode == 0, r.stderr
    call = log.read_text()
    assert "https://api.example.com/api/fleet/maintenance/report" in call
    assert "X-Fleet-Token: tok" in call
    assert '"job":"backup-fleet"' in call
    assert '"status":"success"' in call


def test_fleet_backup_reports_failure_to_maintenance_endpoint(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    backups = tmp_path / "backups"
    log = tmp_path / "curl_calls.log"
    _fake_docker(fakebin, r"""
        case "$1" in
          ps)   echo "broken_db" ;;
          exec) exit 1 ;;
        esac
    """)
    _fake_curl(fakebin, log)

    r = _run("backup-fleet.sh", fakebin, tmp_path, BACKUP_DIR=backups.as_posix(),
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok")

    assert r.returncode == 1
    assert '"status":"failure"' in log.read_text()


def test_fleet_backup_skips_reporting_without_fleet_url(tmp_path):
    # Hors cron (lancement manuel sans FLEET_URL) : aucun appel curl tenté,
    # et surtout pas d'échec du script à cause de ça.
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    backups = tmp_path / "backups"
    log = tmp_path / "curl_calls.log"
    _fake_docker_two_projects(fakebin)
    _fake_curl(fakebin, log)

    r = _run("backup-fleet.sh", fakebin, tmp_path, BACKUP_DIR=backups.as_posix(), FLEET_URL="")

    assert r.returncode == 0, r.stderr
    assert not log.exists()


def test_fleet_backup_loops_containers_not_pg_database(tmp_path):
    # Écart au livre acté : on énumère via `docker ps` (conteneurs), jamais via
    # `SELECT datname FROM pg_database` d'une instance partagée.
    body = (SHARED_SCRIPTS / "backup-fleet.sh").read_text(encoding="utf-8")
    code = "\n".join(l for l in body.splitlines() if not l.lstrip().startswith("#"))
    assert "docker ps" in code
    assert "pg_database" not in code


# --- test-restore-fleet.sh --------------------------------------------------


def _fake_docker_restore(fakebin: Path, *, table_count: str = "3") -> None:
    # run/rm : succès silencieux. exec : dispatche sur la sous-commande réelle
    # (pg_isready/pg_restore/psql), peu importe où "-i" tombe dans les args.
    _fake_docker(fakebin, rf"""
        case "$1" in
          run) exit 0 ;;
          rm)  exit 0 ;;
          exec)
            case "$*" in
              *pg_isready*) exit 0 ;;
              *pg_restore*) cat >/dev/null; exit 0 ;;
              *psql*) echo "{table_count}" ;;
            esac
            ;;
        esac
    """)


def test_fleet_restore_picks_a_project_and_succeeds(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    backups = tmp_path / "backups"; backups.mkdir()
    (backups / "pain_scraper_20260101_020000.dump.gz").write_bytes(b"\x1f\x8b\x00")
    (backups / "launch_me_20260101_020000.dump.gz").write_bytes(b"\x1f\x8b\x00")
    _fake_docker_restore(fakebin)

    r = _run("test-restore-fleet.sh", fakebin, tmp_path, BACKUP_DIR=backups.as_posix())

    assert r.returncode == 0, r.stderr
    assert "Test de restauration réussi" in r.stdout
    assert any(name in r.stdout for name in ("pain_scraper", "launch_me"))


def test_fleet_restore_respects_project_override(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    backups = tmp_path / "backups"; backups.mkdir()
    (backups / "pain_scraper_20260101_020000.dump.gz").write_bytes(b"\x1f\x8b\x00")
    (backups / "launch_me_20260101_020000.dump.gz").write_bytes(b"\x1f\x8b\x00")
    _fake_docker_restore(fakebin)

    # PROJECT force le choix plutôt que le tirage au sort — tiret converti en
    # underscore, même convention que backup-fleet.sh.
    r = _run("test-restore-fleet.sh", fakebin, tmp_path,
             BACKUP_DIR=backups.as_posix(), PROJECT="launch-me")

    assert r.returncode == 0, r.stderr
    assert "launch_me" in r.stdout
    assert "pain_scraper" not in r.stdout


def test_fleet_restore_fails_when_no_backups_found(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    backups = tmp_path / "backups"; backups.mkdir()
    _fake_docker_restore(fakebin)

    r = _run("test-restore-fleet.sh", fakebin, tmp_path, BACKUP_DIR=backups.as_posix())

    assert r.returncode == 1
    assert "aucune sauvegarde trouvée" in r.stdout


def test_fleet_restore_fails_when_restored_table_count_is_zero(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    backups = tmp_path / "backups"; backups.mkdir()
    (backups / "pain_scraper_20260101_020000.dump.gz").write_bytes(b"\x1f\x8b\x00")
    _fake_docker_restore(fakebin, table_count="0")

    r = _run("test-restore-fleet.sh", fakebin, tmp_path, BACKUP_DIR=backups.as_posix())

    assert r.returncode == 1
    assert "aucune table après restauration" in r.stdout


def test_fleet_restore_cleans_up_container_on_exit(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    backups = tmp_path / "backups"; backups.mkdir()
    (backups / "pain_scraper_20260101_020000.dump.gz").write_bytes(b"\x1f\x8b\x00")
    log = tmp_path / "docker_calls.log"
    _fake_docker(fakebin, rf"""
        echo "$@" >> "{log.as_posix()}"
        case "$1" in
          run) exit 0 ;;
          rm)  exit 0 ;;
          exec)
            case "$*" in
              *pg_isready*) exit 0 ;;
              *pg_restore*) cat >/dev/null; exit 0 ;;
              *psql*) echo "3" ;;
            esac
            ;;
        esac
    """)

    r = _run("test-restore-fleet.sh", fakebin, tmp_path, BACKUP_DIR=backups.as_posix())

    assert r.returncode == 0, r.stderr
    calls = log.read_text()
    assert "rm -f gitsky_restore_test_" in calls


def test_fleet_restore_reports_success_to_maintenance_endpoint(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    backups = tmp_path / "backups"; backups.mkdir()
    (backups / "pain_scraper_20260101_020000.dump.gz").write_bytes(b"\x1f\x8b\x00")
    curl_log = tmp_path / "curl_calls.log"
    _fake_docker_restore(fakebin)
    _fake_curl(fakebin, curl_log)

    r = _run("test-restore-fleet.sh", fakebin, tmp_path, BACKUP_DIR=backups.as_posix(),
              PROJECT="pain-scraper", FLEET_URL="https://api.example.com",
              FLEET_REGISTER_TOKEN="tok")

    assert r.returncode == 0, r.stderr
    call = curl_log.read_text()
    assert '"job":"restore-test"' in call
    assert '"status":"success"' in call
    assert '"project":"pain_scraper"' in call


def test_fleet_restore_reports_failure_when_no_backups_found(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    backups = tmp_path / "backups"; backups.mkdir()
    curl_log = tmp_path / "curl_calls.log"
    _fake_docker_restore(fakebin)
    _fake_curl(fakebin, curl_log)

    r = _run("test-restore-fleet.sh", fakebin, tmp_path, BACKUP_DIR=backups.as_posix(),
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok")

    assert r.returncode == 1
    call = curl_log.read_text()
    assert '"job":"restore-test"' in call
    assert '"status":"failure"' in call
    assert '"project":null' in call  # aucun projet n'a encore été tiré au sort


def test_fleet_restore_reports_failure_when_table_count_is_zero(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    backups = tmp_path / "backups"; backups.mkdir()
    (backups / "pain_scraper_20260101_020000.dump.gz").write_bytes(b"\x1f\x8b\x00")
    curl_log = tmp_path / "curl_calls.log"
    _fake_docker_restore(fakebin, table_count="0")
    _fake_curl(fakebin, curl_log)

    r = _run("test-restore-fleet.sh", fakebin, tmp_path, BACKUP_DIR=backups.as_posix(),
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok")

    assert r.returncode == 1
    call = curl_log.read_text()
    assert '"status":"failure"' in call
    assert '"project":"pain_scraper"' in call


def test_fleet_restore_skips_reporting_without_fleet_url(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    backups = tmp_path / "backups"; backups.mkdir()
    (backups / "pain_scraper_20260101_020000.dump.gz").write_bytes(b"\x1f\x8b\x00")
    curl_log = tmp_path / "curl_calls.log"
    _fake_docker_restore(fakebin)
    _fake_curl(fakebin, curl_log)

    r = _run("test-restore-fleet.sh", fakebin, tmp_path,
              BACKUP_DIR=backups.as_posix(), FLEET_URL="")

    assert r.returncode == 0, r.stderr
    assert not curl_log.exists()


# --- fleet-health.sh ---------------------------------------------------------


def _fake_docker_health(fakebin: Path, *, probe_ok: bool = True) -> None:
    # ps -> un backend "pain-scraper_backend" ; exec -> simule le VRAI
    # conteneur (image sans curl, Chap 21) : toute invocation contenant
    # "curl" échoue en 127 ("not found"), le reste (la sonde Python
    # attendue) réussit selon probe_ok.
    _fake_docker(fakebin, rf"""
        case "$1" in
          ps)   echo "pain-scraper_backend" ;;
          exec)
            case "$*" in
              *curl*) exit 127 ;;
              *) {"exit 0" if probe_ok else "exit 1"} ;;
            esac
            ;;
        esac
    """)


def test_fleet_health_updates_state_via_python_probe_not_curl(tmp_path):
    # Bug réel de prod (trouvé en vérifiant le monitoring après un
    # redéploiement de flotte) : les images backend GitSky n'ont pas curl
    # (Chap 21, le HEALTHCHECK du Dockerfile sonde déjà en Python) — un
    # `docker exec ... curl` échouait TOUJOURS en silence (127), l'état ne
    # se mettait jamais à jour, et chaque projet finissait par être déclaré
    # deployment_failed après 5 min alors qu'il tournait normalement.
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    state = tmp_path / "state" / "fleet-health.state"
    curl_log = tmp_path / "curl_calls.log"
    _fake_docker_health(fakebin, probe_ok=True)
    _fake_curl(fakebin, curl_log)

    r = _run("fleet-health.sh", fakebin, tmp_path,
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok",
              STATE_FILE=state.as_posix())

    assert r.returncode == 0, r.stderr
    assert state.exists() and "pain-scraper=" in state.read_text()
    call = curl_log.read_text()
    assert '"last_success":{"pain-scraper"' in call


def test_fleet_health_leaves_state_unset_when_probe_fails(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    state = tmp_path / "state" / "fleet-health.state"
    curl_log = tmp_path / "curl_calls.log"
    _fake_docker_health(fakebin, probe_ok=False)
    _fake_curl(fakebin, curl_log)

    r = _run("fleet-health.sh", fakebin, tmp_path,
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok",
              STATE_FILE=state.as_posix())

    assert r.returncode == 0, r.stderr
    assert state.read_text().strip() == ""
    assert '"last_success":{}' in curl_log.read_text()


def test_fleet_health_probe_never_invokes_curl_inside_container():
    # Garde-fou statique : la sonde interne au conteneur doit rester en
    # Python — curl n'existe dans aucune image backend GitSky.
    body = (SHARED_SCRIPTS / "fleet-health.sh").read_text(encoding="utf-8")
    # Isole la commande `if docker exec ... python -c '...'` (multiligne) du
    # reste du script (qui, lui, invoque légitimement curl pour le POST final
    # vers /api/fleet/projects/health-sweep, et en parle en commentaire) —
    # ancre sur la forme exacte de l'appel, pas sur "docker exec" seul (qui
    # apparaît aussi, en toutes lettres, dans le commentaire expliquant le bug).
    probe = body.split("if docker exec", 1)[1].split("' >/dev/null", 1)[0]
    assert "curl" not in probe
    assert "python -c" in body


# --- fleet-disk.sh -----------------------------------------------------------


def _fake_docker_system_df(fakebin: Path) -> None:
    _fake_docker(fakebin, 'case "$1" in system) exit 0 ;; esac')


def test_fleet_disk_reports_to_maintenance_endpoint(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    log = tmp_path / "curl_calls.log"
    _fake_docker_system_df(fakebin)
    _fake_curl(fakebin, log)

    r = _run("fleet-disk.sh", fakebin, tmp_path,
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok")

    assert r.returncode == 0, r.stderr
    call = log.read_text()
    assert '"job":"disk-check"' in call
    assert '"status":"success"' in call
    assert "Disque / :" in call


def test_fleet_disk_skips_reporting_without_fleet_url(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    log = tmp_path / "curl_calls.log"
    _fake_docker_system_df(fakebin)
    _fake_curl(fakebin, log)

    r = _run("fleet-disk.sh", fakebin, tmp_path, FLEET_URL="")

    assert r.returncode == 0, r.stderr
    assert not log.exists()


# --- deploy-on-push.sh ------------------------------------------------------


def _fake_curl_deploy(fakebin: Path, log: Path, *, pending: str = "") -> None:
    # GET (pas de "-X POST" dans les args) -> répond `pending` sur stdout
    # (simule /api/fleet/deploys/pending). POST -> journalise l'appel (report),
    # même patron que _fake_curl mais avec un corps de réponse pour le GET.
    c = fakebin / "curl"
    _write_lf(
        c,
        "#!/usr/bin/env bash\n"
        f'echo "$@" >> "{log.as_posix()}"\n'
        'if [[ "$*" == *"-X POST"* ]]; then\n'
        "  exit 0\n"
        "fi\n"
        f'printf %s "{pending}"\n',
    )
    c.chmod(0o755)


def _fake_git(fakebin: Path, *, fail: bool = False) -> None:
    g = fakebin / "git"
    _write_lf(g, "#!/usr/bin/env bash\n" + ("exit 1\n" if fail else "exit 0\n"))
    g.chmod(0o755)


def _fake_docker_deploy(fakebin: Path, *, compose_fails: bool = False, health_fails: bool = False) -> None:
    _fake_docker(fakebin, rf"""
        case "$1" in
          compose) {"exit 1" if compose_fails else "exit 0"} ;;
          exec)    {"exit 1" if health_fails else "exit 0"} ;;
        esac
    """)


def _make_project_dirs(base: Path, *names: str) -> Path:
    for name in names:
        (base / name).mkdir(parents=True, exist_ok=True)
    return base


def test_deploy_redeploys_every_pending_project_and_advances_cursor(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    projects = _make_project_dirs(tmp_path / "projects", "pain-scraper", "launch-me")
    curl_log = tmp_path / "curl_calls.log"
    _fake_curl_deploy(fakebin, curl_log, pending="5\tpain-scraper\n6\tlaunch-me")
    _fake_git(fakebin)
    _fake_docker_deploy(fakebin)
    state = tmp_path / "state" / "deploy.state"

    r = _run("deploy-on-push.sh", fakebin, tmp_path,
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok",
              PROJECTS_DIR=projects.as_posix(), STATE_FILE=state.as_posix())

    assert r.returncode == 0, r.stderr
    assert state.read_text().strip() == "6"
    calls = curl_log.read_text()
    assert calls.count('"status":"success"') == 2
    assert '"project":"pain-scraper"' in calls
    assert '"project":"launch-me"' in calls


def test_deploy_reports_failure_when_project_directory_missing(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    projects = tmp_path / "projects"; projects.mkdir()  # "ghost" n'existe pas dedans
    curl_log = tmp_path / "curl_calls.log"
    _fake_curl_deploy(fakebin, curl_log, pending="9\tghost")
    _fake_git(fakebin)
    _fake_docker_deploy(fakebin)
    state = tmp_path / "state" / "deploy.state"

    r = _run("deploy-on-push.sh", fakebin, tmp_path,
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok",
              PROJECTS_DIR=projects.as_posix(), STATE_FILE=state.as_posix())

    assert r.returncode == 1
    assert '"status":"failure"' in curl_log.read_text()
    assert '"project":"ghost"' in curl_log.read_text()
    # Le curseur avance quand même : un projet cassé ne doit pas bloquer les
    # suivants indéfiniment.
    assert state.read_text().strip() == "9"


def test_deploy_reports_failure_when_git_pull_diverges(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    projects = _make_project_dirs(tmp_path / "projects", "pain-scraper")
    curl_log = tmp_path / "curl_calls.log"
    _fake_curl_deploy(fakebin, curl_log, pending="1\tpain-scraper")
    _fake_git(fakebin, fail=True)  # simule un git pull --ff-only refusé
    _fake_docker_deploy(fakebin)
    state = tmp_path / "state" / "deploy.state"

    r = _run("deploy-on-push.sh", fakebin, tmp_path,
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok",
              PROJECTS_DIR=projects.as_posix(), STATE_FILE=state.as_posix())

    assert r.returncode == 1
    assert '"status":"failure"' in curl_log.read_text()


def test_deploy_reports_failure_when_health_check_fails_after_build(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    projects = _make_project_dirs(tmp_path / "projects", "pain-scraper")
    curl_log = tmp_path / "curl_calls.log"
    _fake_curl_deploy(fakebin, curl_log, pending="1\tpain-scraper")
    _fake_git(fakebin)
    _fake_docker_deploy(fakebin, health_fails=True)
    state = tmp_path / "state" / "deploy.state"

    r = _run("deploy-on-push.sh", fakebin, tmp_path,
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok",
              PROJECTS_DIR=projects.as_posix(), STATE_FILE=state.as_posix())

    assert r.returncode == 1
    call = curl_log.read_text()
    assert '"status":"failure"' in call
    assert "health" in call


def _fake_docker_deploy_realistic_probe(fakebin: Path) -> None:
    # compose/git : succès silencieux. exec : simule le VRAI conteneur
    # backend (Chap 21, sans curl) - toute invocation contenant "curl"
    # échoue en 127, la sonde Python attendue réussit.
    _fake_docker(fakebin, r"""
        case "$1" in
          compose) exit 0 ;;
          exec)
            case "$*" in
              *curl*) exit 127 ;;
              *) exit 0 ;;
            esac
            ;;
        esac
    """)


def test_deploy_reports_success_via_python_probe_not_curl(tmp_path):
    # Bug réel de prod, trouvé en vérifiant un vrai cycle de redeploy bout en
    # bout : `docker exec ... curl` échoue TOUJOURS en silence (127) contre
    # les images backend GitSky (pas de curl, Chap 21) - le redeploy
    # réussissait réellement mais était systématiquement rapporté en échec.
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    projects = _make_project_dirs(tmp_path / "projects", "pain-scraper")
    curl_log = tmp_path / "curl_calls.log"
    _fake_curl_deploy(fakebin, curl_log, pending="1\tpain-scraper")
    _fake_git(fakebin)
    _fake_docker_deploy_realistic_probe(fakebin)
    state = tmp_path / "state" / "deploy.state"

    r = _run("deploy-on-push.sh", fakebin, tmp_path,
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok",
              PROJECTS_DIR=projects.as_posix(), STATE_FILE=state.as_posix())

    assert r.returncode == 0, r.stderr
    assert '"status":"success"' in curl_log.read_text()


def test_deploy_probe_never_invokes_curl_inside_container():
    # Garde-fou statique : la sonde interne au conteneur doit rester en
    # Python — curl n'existe dans aucune image backend GitSky.
    body = (SHARED_SCRIPTS / "deploy-on-push.sh").read_text(encoding="utf-8")
    probe = body.split("if docker exec", 1)[1].split("' >/dev/null", 1)[0]
    assert "curl" not in probe
    assert "python -c" in body


def test_deploy_exits_cleanly_when_nothing_pending(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    curl_log = tmp_path / "curl_calls.log"
    _fake_curl_deploy(fakebin, curl_log, pending="")
    _fake_git(fakebin)
    _fake_docker_deploy(fakebin)
    state = tmp_path / "state" / "deploy.state"

    r = _run("deploy-on-push.sh", fakebin, tmp_path,
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok",
              PROJECTS_DIR=(tmp_path / "projects").as_posix(), STATE_FILE=state.as_posix())

    assert r.returncode == 0, r.stderr
    # Aucun report : seul le GET (fetch pending) a été appelé.
    assert "-X POST" not in curl_log.read_text()


def test_deploy_resumes_from_existing_state_file_cursor(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    projects = _make_project_dirs(tmp_path / "projects", "launch-me")
    curl_log = tmp_path / "curl_calls.log"
    _fake_curl_deploy(fakebin, curl_log, pending="42\tlaunch-me")
    _fake_git(fakebin)
    _fake_docker_deploy(fakebin)
    state = tmp_path / "state" / "deploy.state"
    state.parent.mkdir(parents=True)
    state.write_text("20\n")

    r = _run("deploy-on-push.sh", fakebin, tmp_path,
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok",
              PROJECTS_DIR=projects.as_posix(), STATE_FILE=state.as_posix())

    assert r.returncode == 0, r.stderr
    # Le curseur précédent (20) doit avoir été envoyé comme since_id.
    assert "since_id=20" in curl_log.read_text()
    assert state.read_text().strip() == "42"


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


# --- lifecycle-fleet.sh (Chap 20/23, round sécurisation) --------------------


def _fake_curl_lifecycle(fakebin: Path, log: Path, *, pending: str = "") -> None:
    # Même patron que _fake_curl_deploy : GET (pas de "-X POST") -> répond
    # `pending` (simule /api/fleet/lifecycle/pending). POST -> journalise.
    c = fakebin / "curl"
    _write_lf(
        c,
        "#!/usr/bin/env bash\n"
        f'echo "$@" >> "{log.as_posix()}"\n'
        'if [[ "$*" == *"-X POST"* ]]; then\n'
        "  exit 0\n"
        "fi\n"
        f'printf %s "{pending}"\n',
    )
    c.chmod(0o755)


def _fake_docker_lifecycle(fakebin: Path, *, fails: bool = False) -> None:
    # Journalise chaque invocation (args complets) pour vérifier la bonne
    # commande par action, sans jamais toucher un vrai Docker.
    arglog = (fakebin / "docker_calls.log").as_posix()
    _fake_docker(fakebin, rf"""
        echo "$@" >> "{arglog}"
        case "$1" in
          compose) {"exit 1" if fails else "exit 0"} ;;
        esac
    """)


def test_lifecycle_stop_runs_compose_down(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    projects = _make_project_dirs(tmp_path / "projects", "pain-scraper")
    curl_log = tmp_path / "curl_calls.log"
    _fake_curl_lifecycle(fakebin, curl_log, pending="1\tpain-scraper\tstop")
    _fake_docker_lifecycle(fakebin)
    state = tmp_path / "state" / "lifecycle.state"

    r = _run("lifecycle-fleet.sh", fakebin, tmp_path,
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok",
              PROJECTS_DIR=projects.as_posix(), STATE_FILE=state.as_posix())

    assert r.returncode == 0, r.stderr
    calls = (fakebin / "docker_calls.log").read_text(encoding="utf-8")
    assert "compose down" in calls
    assert "compose up" not in calls
    assert '"status":"success"' in curl_log.read_text()
    assert state.read_text().strip() == "1"


def test_lifecycle_start_runs_compose_up_without_build(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    projects = _make_project_dirs(tmp_path / "projects", "pain-scraper")
    curl_log = tmp_path / "curl_calls.log"
    _fake_curl_lifecycle(fakebin, curl_log, pending="2\tpain-scraper\tstart")
    _fake_docker_lifecycle(fakebin)
    state = tmp_path / "state" / "lifecycle.state"

    r = _run("lifecycle-fleet.sh", fakebin, tmp_path,
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok",
              PROJECTS_DIR=projects.as_posix(), STATE_FILE=state.as_posix())

    assert r.returncode == 0, r.stderr
    calls = (fakebin / "docker_calls.log").read_text(encoding="utf-8")
    # Pas de --build : l'image existe déjà, seul un redéploiement en
    # rebuild une (deploy-on-push.sh), pas un simple redémarrage.
    assert "compose up -d" in calls
    assert "--build" not in calls


def test_lifecycle_maintenance_stops_real_app_then_starts_maintenance_compose(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    projects = _make_project_dirs(tmp_path / "projects", "pain-scraper")
    curl_log = tmp_path / "curl_calls.log"
    _fake_curl_lifecycle(fakebin, curl_log, pending="3\tpain-scraper\tmaintenance")
    _fake_docker_lifecycle(fakebin)
    state = tmp_path / "state" / "lifecycle.state"

    r = _run("lifecycle-fleet.sh", fakebin, tmp_path,
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok",
              PROJECTS_DIR=projects.as_posix(), STATE_FILE=state.as_posix())

    assert r.returncode == 0, r.stderr
    calls = (fakebin / "docker_calls.log").read_text(encoding="utf-8").splitlines()
    down_idx = next(i for i, c in enumerate(calls) if c == "compose down")
    up_idx = next(
        i for i, c in enumerate(calls)
        if c == "compose -f docker-compose.maintenance.yml up -d"
    )
    assert down_idx < up_idx, "le compose réel doit être arrêté AVANT que la maintenance démarre"


def test_lifecycle_maintenance_clear_reverses_the_swap(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    projects = _make_project_dirs(tmp_path / "projects", "pain-scraper")
    curl_log = tmp_path / "curl_calls.log"
    _fake_curl_lifecycle(fakebin, curl_log, pending="4\tpain-scraper\tmaintenance-clear")
    _fake_docker_lifecycle(fakebin)
    state = tmp_path / "state" / "lifecycle.state"

    r = _run("lifecycle-fleet.sh", fakebin, tmp_path,
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok",
              PROJECTS_DIR=projects.as_posix(), STATE_FILE=state.as_posix())

    assert r.returncode == 0, r.stderr
    calls = (fakebin / "docker_calls.log").read_text(encoding="utf-8").splitlines()
    down_idx = next(
        i for i, c in enumerate(calls)
        if c == "compose -f docker-compose.maintenance.yml down"
    )
    up_idx = next(i for i, c in enumerate(calls) if c == "compose up -d")
    assert down_idx < up_idx, "la maintenance doit être arrêtée AVANT que l'app réelle redémarre"


def test_lifecycle_reports_failure_for_unknown_action(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    projects = _make_project_dirs(tmp_path / "projects", "pain-scraper")
    curl_log = tmp_path / "curl_calls.log"
    _fake_curl_lifecycle(fakebin, curl_log, pending="5\tpain-scraper\tsomething-else")
    _fake_docker_lifecycle(fakebin)
    state = tmp_path / "state" / "lifecycle.state"

    r = _run("lifecycle-fleet.sh", fakebin, tmp_path,
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok",
              PROJECTS_DIR=projects.as_posix(), STATE_FILE=state.as_posix())

    assert r.returncode == 1
    assert '"status":"failure"' in curl_log.read_text()
    # Le curseur avance quand même — même logique que deploy-on-push.sh.
    assert state.read_text().strip() == "5"


def test_lifecycle_reports_failure_when_project_directory_missing(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    projects = tmp_path / "projects"; projects.mkdir()  # "ghost" n'existe pas dedans
    curl_log = tmp_path / "curl_calls.log"
    _fake_curl_lifecycle(fakebin, curl_log, pending="6\tghost\tstop")
    _fake_docker_lifecycle(fakebin)
    state = tmp_path / "state" / "lifecycle.state"

    r = _run("lifecycle-fleet.sh", fakebin, tmp_path,
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok",
              PROJECTS_DIR=projects.as_posix(), STATE_FILE=state.as_posix())

    assert r.returncode == 1
    assert '"status":"failure"' in curl_log.read_text()
    assert '"project":"ghost"' in curl_log.read_text()


def test_lifecycle_exits_cleanly_when_nothing_pending(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    curl_log = tmp_path / "curl_calls.log"
    _fake_curl_lifecycle(fakebin, curl_log, pending="")
    _fake_docker_lifecycle(fakebin)
    state = tmp_path / "state" / "lifecycle.state"

    r = _run("lifecycle-fleet.sh", fakebin, tmp_path,
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok",
              PROJECTS_DIR=(tmp_path / "projects").as_posix(), STATE_FILE=state.as_posix())

    assert r.returncode == 0, r.stderr
    assert "-X POST" not in curl_log.read_text()


def test_lifecycle_processes_multiple_pending_actions_and_advances_cursor(tmp_path):
    fakebin = tmp_path / "bin"; fakebin.mkdir()
    projects = _make_project_dirs(tmp_path / "projects", "pain-scraper", "launch-me")
    curl_log = tmp_path / "curl_calls.log"
    _fake_curl_lifecycle(
        fakebin, curl_log, pending="7\tpain-scraper\tstop\n8\tlaunch-me\tstart"
    )
    _fake_docker_lifecycle(fakebin)
    state = tmp_path / "state" / "lifecycle.state"

    r = _run("lifecycle-fleet.sh", fakebin, tmp_path,
              FLEET_URL="https://api.example.com", FLEET_REGISTER_TOKEN="tok",
              PROJECTS_DIR=projects.as_posix(), STATE_FILE=state.as_posix())

    assert r.returncode == 0, r.stderr
    assert state.read_text().strip() == "8"
    calls = curl_log.read_text()
    assert calls.count('"status":"success"') == 2
