"""Scripts d'exploitation post-génération : bascule de module, création
d'admin (Chap 2/7/17, round outillage). Même patron de test que
test_rotate_scripts.py : un faux `docker` en tête de PATH, aucun démon requis
— ces scripts tournent sur l'HÔTE, pas dans le conteneur.
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


def _run(script: Path, project: Path, fakebin: Path, *args: str, **env_over) -> subprocess.CompletedProcess:
    dst_scripts = project / "scripts"
    dst_scripts.mkdir(exist_ok=True)
    shutil.copy(script, dst_scripts / script.name)

    env = dict(os.environ)
    env["PATH"] = str(fakebin) + os.pathsep + env["PATH"]
    env["HEALTH_CHECK_RETRIES"] = "1"
    env["HEALTH_CHECK_DELAY"] = "0"
    env.update(env_over)
    return subprocess.run(
        [BASH, str(dst_scripts / script.name), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, cwd=str(project),
    )


def _fake_docker(fakebin: Path, body: str) -> None:
    _make_fake_bin(fakebin, "docker", body)


def _write_env(project: Path, **kv) -> None:
    _write_lf(project / ".env", "\n".join(f"{k}={v}" for k, v in kv.items()) + "\n")


def _write_answers(project: Path, modules: str = "{}") -> None:
    _write_lf(
        project / ".copier-answers.yml",
        f"_src_path: gitsky-template\nmodules: {modules}\n"
        "project:\n    domain: pain-scraper.mystudio.com\n    name: pain-scraper\n",
    )


def _base_env(**over) -> dict:
    base = {
        "PROJECT_NAME": "pain-scraper",
        "POSTGRES_USER": "pain_scraper",
        "POSTGRES_DB": "pain_scraper",
        "MODULE_ADMIN": "false",
        "MODULE_ANALYTICS": "false",
        "MODULE_FLEET": "false",
    }
    base.update(over)
    return base


# --- toggle_module.sh --------------------------------------------------


def test_toggle_rejects_fleet_module(project, fakebin):
    _write_env(project, **_base_env())
    r = _run(SCRIPTS / "toggle_module.sh", project, fakebin, "fleet", "on")
    assert r.returncode == 1
    assert "copier update" in r.stderr


def test_toggle_rejects_invalid_state(project, fakebin):
    _write_env(project, **_base_env())
    r = _run(SCRIPTS / "toggle_module.sh", project, fakebin, "admin", "maybe")
    assert r.returncode == 1
    assert "État invalide" in r.stderr


def test_toggle_rejects_unknown_module(project, fakebin):
    _write_env(project, **_base_env())
    r = _run(SCRIPTS / "toggle_module.sh", project, fakebin, "nonexistent", "on")
    assert r.returncode == 1
    assert "Module inconnu" in r.stderr
    assert "admin" in r.stderr  # le catalogue listé inclut les modules réels


def test_toggle_is_noop_when_already_in_requested_state(project, fakebin):
    _write_env(project, **_base_env(MODULE_ADMIN="true"))
    arglog = (project / "docker_args.log").as_posix()
    _fake_docker(fakebin, f'echo "$@" >> "{arglog}"')

    r = _run(SCRIPTS / "toggle_module.sh", project, fakebin, "admin", "on")

    assert r.returncode == 0, r.stderr
    assert "déjà" in r.stdout
    assert not (project / "docker_args.log").exists()


def _fake_docker_toggle(fakebin: Path, *, probe_result: str = "on") -> None:
    arglog = (fakebin / "args.log").as_posix()
    _fake_docker(fakebin, rf"""
        echo "$@" >> "{arglog}"
        case "$1" in
          compose) exit 0 ;;
          exec)    echo "{probe_result}" ;;
        esac
    """)


def test_toggle_flips_flag_migrates_recreates_and_confirms(project, fakebin):
    _write_env(project, **_base_env(MODULE_ADMIN="false"))
    _write_answers(project)
    _fake_docker_toggle(fakebin, probe_result="on")

    r = _run(SCRIPTS / "toggle_module.sh", project, fakebin, "admin", "on")

    assert r.returncode == 0, r.stderr
    assert "MODULE_ADMIN=true" in (project / ".env").read_text(encoding="utf-8")
    calls = (fakebin / "args.log").read_text(encoding="utf-8")
    assert "run --rm migrate" in calls
    assert "compose up -d --force-recreate backend" in calls
    assert "confirmé via /health" in r.stdout


def test_toggle_also_updates_copier_answers_so_the_flag_survives_copier_update(project, fakebin):
    # Bug de prod réel : sans cette étape, un copier update ultérieur re-rend
    # .env.jinja depuis la réponse `modules:` STOCKÉE (jamais depuis .env) et
    # écrase silencieusement le flag tout juste basculé — trouvé en
    # retrouvant MODULE_ADMIN=false sur politique-ia le lendemain d'un
    # `toggle_module.sh admin on` réussi, un copier update entre les deux.
    _write_env(project, **_base_env(MODULE_ADMIN="false"))
    _write_answers(project, modules="{}")
    _fake_docker_toggle(fakebin, probe_result="on")

    r = _run(SCRIPTS / "toggle_module.sh", project, fakebin, "admin", "on")

    assert r.returncode == 0, r.stderr
    answers = (project / ".copier-answers.yml").read_text(encoding="utf-8")
    assert "modules: {admin: true}" in answers
    assert "écrit dans .copier-answers.yml" in r.stdout


def test_toggle_reads_block_style_modules_without_duplicating_the_key(project, fakebin):
    # copier réécrit lui-même .copier-answers.yml en style bloc au fil des
    # `copier update` (constaté sur politique-ia, pas documenté) — le style
    # flow n'est garanti qu'à la création. Sans ce test, une régression ici
    # dupliquerait silencieusement la clé `modules:` au lieu de la fusionner.
    _write_env(project, **_base_env(MODULE_ADMIN="false", MODULE_FLEET="true"))
    _write_lf(
        project / ".copier-answers.yml",
        "_src_path: gitsky-template\nmodules:\n    fleet: true\nproject:\n"
        "    domain: pain-scraper.mystudio.com\n    name: pain-scraper\n",
    )
    _fake_docker_toggle(fakebin, probe_result="on")

    r = _run(SCRIPTS / "toggle_module.sh", project, fakebin, "admin", "on")

    assert r.returncode == 0, r.stderr
    answers = (project / ".copier-answers.yml").read_text(encoding="utf-8")
    assert answers.count("modules:") == 1
    assert "fleet: true" in answers
    assert "admin: true" in answers


def test_toggle_preserves_other_modules_already_in_copier_answers(project, fakebin):
    _write_env(project, **_base_env(MODULE_ADMIN="false", MODULE_FLEET="true"))
    _write_answers(project, modules="{fleet: true}")
    _fake_docker_toggle(fakebin, probe_result="on")

    r = _run(SCRIPTS / "toggle_module.sh", project, fakebin, "admin", "on")

    assert r.returncode == 0, r.stderr
    answers = (project / ".copier-answers.yml").read_text(encoding="utf-8")
    assert "fleet: true" in answers
    assert "admin: true" in answers


def test_toggle_reports_failure_when_health_never_confirms(project, fakebin):
    _write_env(project, **_base_env(MODULE_ADMIN="false"))
    _write_answers(project)
    _fake_docker_toggle(fakebin, probe_result="off")  # jamais "on", même après le flip

    r = _run(SCRIPTS / "toggle_module.sh", project, fakebin, "admin", "on")

    assert r.returncode == 1
    assert "vérifier manuellement" in r.stderr
    # Le flag EST écrit dans .env malgré l'échec de la confirmation — pas de
    # rollback silencieux, l'opérateur voit l'état réel du fichier.
    assert "MODULE_ADMIN=true" in (project / ".env").read_text(encoding="utf-8")


def test_toggle_off_flips_flag_the_other_way(project, fakebin):
    _write_env(project, **_base_env(MODULE_ADMIN="true"))
    _write_answers(project, modules="{admin: true}")
    _fake_docker_toggle(fakebin, probe_result="off")

    r = _run(SCRIPTS / "toggle_module.sh", project, fakebin, "admin", "off")

    assert r.returncode == 0, r.stderr
    assert "MODULE_ADMIN=false" in (project / ".env").read_text(encoding="utf-8")
    assert "modules: {admin: false}" in (project / ".copier-answers.yml").read_text(encoding="utf-8")


# --- create_admin.sh -----------------------------------------------------


def _fake_docker_admin(fakebin: Path, *, register_result: str = "created") -> None:
    arglog = (fakebin / "args.log").as_posix()
    stdinlog = (fakebin / "stdin.log").as_posix()
    _fake_docker(fakebin, rf"""
        echo "$@" >> "{arglog}"
        case "$*" in
          *_backend*) echo "{register_result}" ;;
          # Bug de prod réel (cryptokilla, 2026-08-30) : le script réel passe
          # désormais le SQL par stdin (`docker exec -i ... <<< "..."`), pas
          # par `-c` — psql n'interpole `:'email'` que pour un script lu sur
          # stdin/-f, jamais pour -c. Le faux docker capture donc stdin ici
          # pour que le test puisse vérifier CE que psql recevrait réellement,
          # pas seulement les arguments de la ligne de commande.
          *_db*) cat > "{stdinlog}"; exit 0 ;;
        esac
    """)


def test_create_admin_registers_and_promotes(project, fakebin):
    _write_env(project, **_base_env())
    _fake_docker_admin(fakebin, register_result="created")

    r = _run(SCRIPTS / "create_admin.sh", project, fakebin, "ops@example.com", "S3curePass!")

    assert r.returncode == 0, r.stderr
    assert "Compte créé" in r.stdout
    assert "maintenant admin" in r.stdout
    # Pas de mot de passe généré affiché : il a été fourni explicitement.
    assert "Mot de passe généré" not in r.stdout

    calls = (fakebin / "args.log").read_text(encoding="utf-8")
    assert "REGISTER_EMAIL=ops@example.com" in calls
    assert "pain-scraper_backend" in calls
    assert "email=ops@example.com" in calls  # -v email=... (psql, jamais interpolé dans le SQL)
    db_call = next(line for line in calls.splitlines() if "_db" in line)
    assert "exec -i" in db_call  # stdin requis pour que le SQL ci-dessous soit lu par psql
    assert " -c " not in db_call  # bug réel : -c n'interpole jamais :'email' (cryptokilla, 2026-08-30)
    stdin = (fakebin / "stdin.log").read_text(encoding="utf-8")
    assert "UPDATE users SET role = 'admin'" in stdin


def test_create_admin_generates_and_displays_password_once(project, fakebin):
    _write_env(project, **_base_env())
    _fake_docker_admin(fakebin, register_result="created")

    r = _run(SCRIPTS / "create_admin.sh", project, fakebin, "ops@example.com")

    assert r.returncode == 0, r.stderr
    assert "Mot de passe généré" in r.stdout


def test_create_admin_promotes_existing_account_without_changing_password(project, fakebin):
    _write_env(project, **_base_env())
    _fake_docker_admin(fakebin, register_result="exists")

    r = _run(SCRIPTS / "create_admin.sh", project, fakebin, "ops@example.com")

    assert r.returncode == 0, r.stderr
    assert "existe déjà" in r.stdout
    assert "mot de passe inchangé" in r.stdout
    assert "Mot de passe généré" not in r.stdout
    stdin = (fakebin / "stdin.log").read_text(encoding="utf-8")
    assert "UPDATE users SET role = 'admin'" in stdin


def test_create_admin_fails_on_registration_error_without_promoting(project, fakebin):
    _write_env(project, **_base_env())
    _fake_docker_admin(fakebin, register_result="error:422")

    r = _run(SCRIPTS / "create_admin.sh", project, fakebin, "not-an-email")

    assert r.returncode == 1
    assert not (fakebin / "stdin.log").exists()


def test_create_admin_fails_cleanly_without_postgres_project(project, fakebin):
    _write_env(project, PROJECT_NAME="t0-project")  # pas de POSTGRES_* (projet T0)
    _fake_docker_admin(fakebin)

    r = _run(SCRIPTS / "create_admin.sh", project, fakebin, "ops@example.com")

    assert r.returncode == 1
    assert "POSTGRES" in r.stderr


# --- Qualité des scripts livrés ---------------------------------------------


@pytest.mark.parametrize("name", ["toggle_module.sh", "create_admin.sh"])
def test_module_ops_scripts_pass_bash_syntax_check(name):
    r = subprocess.run([BASH, "-n", str(SCRIPTS / name)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_module_ops_scripts_never_invoke_curl_inside_container():
    for name in ("toggle_module.sh", "create_admin.sh"):
        body = (SCRIPTS / name).read_text(encoding="utf-8")
        code = "\n".join(l for l in body.splitlines() if not l.lstrip().startswith("#"))
        assert "curl" not in code


def test_module_ops_scripts_ship_into_generated_projects():
    with projet_genere("pain-scraper") as dst:
        assert (dst / "scripts" / "toggle_module.sh").is_file()
        assert (dst / "scripts" / "create_admin.sh").is_file()
