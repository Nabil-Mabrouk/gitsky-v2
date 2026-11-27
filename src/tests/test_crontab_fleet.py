"""Crontab de flotte + calendrier de maintenance (Phase 6, incr 7 — Chap 23 §6).

Une crontab ne s'exécute pas en test, mais elle DOIT être cohérente : champs
d'horaire valides, scripts référencés existants, sauvegarde avant test de
restauration, et aucun reliquat `hitl`/`/opt/0-hitl` du livre.
"""

import re
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "shared_services"
CRONTAB = SHARED / "crontab.fleet"
SCRIPTS = SHARED / "scripts"


def _cron_lines() -> list[str]:
    return [
        line.strip()
        for line in CRONTAB.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#") and "=" not in line.split()[0]
    ]


def _schedule_and_command(line: str) -> tuple[list[str], str]:
    # 5 champs d'horaire, puis la commande.
    parts = line.split(maxsplit=5)
    return parts[:5], parts[5]


def test_crontab_exists_and_has_jobs():
    assert CRONTAB.is_file()
    assert len(_cron_lines()) >= 4


def test_every_cron_line_has_five_schedule_fields():
    for line in _cron_lines():
        fields, command = _schedule_and_command(line)
        assert len(fields) == 5, line
        assert command, line
        # Chaque champ n'est fait que de chiffres, *, /, ,, - (syntaxe cron).
        for f in fields:
            assert re.fullmatch(r"[0-9*/,\-]+", f), (f, line)


def test_referenced_fleet_scripts_exist():
    # Un chemin de script qui n'existe pas = cron qui échoue en silence.
    for line in _cron_lines():
        _, command = _schedule_and_command(line)
        for token in command.split():
            if token.startswith("/opt/gitsky/") and token.endswith(".sh"):
                name = Path(token).name
                assert (SCRIPTS / name).is_file(), f"{name} référencé mais absent"


def test_backup_runs_before_restore_test():
    # Le 1er du mois, test-restore-fleet.sh restaure la sauvegarde du jour :
    # elle doit donc déjà exister, donc tourner plus tôt dans la nuit.
    backup_hour = None
    restore_test_hour = None
    for line in _cron_lines():
        fields, command = _schedule_and_command(line)
        if "backup-fleet.sh" in command:
            backup_hour = int(fields[1])  # champ « heure »
        elif "test-restore-fleet.sh" in command:
            restore_test_hour = int(fields[1])
    assert backup_hour is not None, "backup-fleet.sh doit être planifié"
    assert restore_test_hour is not None, "test-restore-fleet.sh doit être planifié"
    assert backup_hour < restore_test_hour, (
        "la sauvegarde doit précéder le test de restauration"
    )


def test_health_poll_runs_every_minute():
    # Muet > 5 min => alerte : il faut un poll par minute pour tenir ce seuil.
    for line in _cron_lines():
        fields, command = _schedule_and_command(line)
        if "fleet-health.sh" in command:
            assert fields == ["*", "*", "*", "*", "*"], "poll santé = chaque minute"
            return
    raise AssertionError("fleet-health.sh doit être planifié")


def test_no_legacy_hitl_paths():
    # Hors commentaires : un commentaire cite légitimement /opt/0-hitl pour
    # expliquer l'écart au livre.
    code = "\n".join(
        line for line in CRONTAB.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("#")
    )
    assert "hitl" not in code
    assert "/opt/0-hitl" not in code


GUIDE = SHARED.parents[1] / "docs" / "exploitation"


def test_maintenance_calendar_present():
    # Le calendrier vit dans le guide d'exploitation publié sur 0-hitl.com
    # (2026-11-27). Il doit couvrir l'automatique ET le manuel (restauration,
    # secrets).
    fleet = (GUIDE / "05-maintenance-de-la-flotte.md").read_text(encoding="utf-8")
    project = (GUIDE / "04-maintenance-d-un-projet.md").read_text(encoding="utf-8")
    assert "backup-fleet.sh" in fleet
    assert "test-restore-fleet.sh" in fleet
    assert "SECRET_KEY" in project
    assert "emergency_restore.sh" in project


def test_every_scheduled_script_is_documented_in_the_guide():
    # Garde-fou de la règle « le guide suit chaque changement » : un script
    # ajouté au cron sans ligne dans le guide fait échouer ce test.
    fleet = (GUIDE / "05-maintenance-de-la-flotte.md").read_text(encoding="utf-8")
    scheduled = set()
    for line in CRONTAB.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("#"):
            continue
        scheduled.update(re.findall(r"scripts/([\w-]+\.sh)", line))
    assert scheduled, "aucun script planifié trouvé"
    missing = sorted(name for name in scheduled if name not in fleet)
    assert not missing, missing


def test_crontab_has_unix_line_endings():
    assert b"\r" not in CRONTAB.read_bytes()
