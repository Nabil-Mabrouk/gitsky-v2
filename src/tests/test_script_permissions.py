"""Bit exécutable des scripts shell invoqués directement (pas via `bash script.sh`).

Trouvé en déploiement réel : crontab.fleet appelle
`/opt/gitsky/shared_services/scripts/fleet-health.sh` directement (pas
`bash fleet-health.sh`) — sans le bit +x, cron échoue avec "Permission
denied". Les tests existants (test_fleet_scripts.py, test_maintenance_scripts.py)
invoquent toujours via `bash <script>`, qui n'exige pas ce bit : c'est
exactement pourquoi le trou est passé inaperçu jusqu'au déploiement.

Vérifie le mode suivi par GIT (`git ls-files -s`), pas `os.stat` sur le
fichier de travail — sur Windows, `os.stat` ne reflète pas fiablement le
bit exécutable que git applique réellement au checkout sur le VPS Linux.

`src/generator/` est un submodule (gitsky-template) depuis la scission qui a
rendu `copier update` fonctionnel — `git ls-files` depuis la racine du
monorepo ne voit pas à l'intérieur (frontière gitlink opaque). Chaque chemin
est donc résolu contre le dépôt qui le suit réellement : le submodule pour
`src/generator/**`, le monorepo sinon.
"""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SUBMODULE_ROOT = REPO_ROOT / "src" / "generator"

# Scripts invoqués directement (crontab.fleet, ou par un opérateur en
# ligne de commande) — le bit +x n'est pas optionnel pour ceux-là.
DIRECTLY_INVOKED_SCRIPTS = [
    "src/shared_services/scripts/backup-fleet.sh",
    "src/shared_services/scripts/fleet-disk.sh",
    "src/shared_services/scripts/fleet-health.sh",
    "src/generator/template/scripts/backup_db.sh",
    "src/generator/template/scripts/check_disk.sh",
    "src/generator/template/scripts/check_errors.sh",
    "src/generator/template/scripts/check_security.sh",
    "src/generator/template/scripts/emergency_restore.sh",
    "src/generator/template/scripts/test_restore.sh",
]


def _git_tracked_mode(path: str) -> str:
    submodule_prefix = "src/generator/"
    if path.startswith(submodule_prefix):
        cwd = SUBMODULE_ROOT
        rel_path = path[len(submodule_prefix):]
    else:
        cwd = REPO_ROOT
        rel_path = path
    out = subprocess.check_output(
        ["git", "ls-files", "-s", rel_path], cwd=str(cwd), text=True
    )
    assert out, f"{path} n'est pas suivi par git"
    return out.split()[0]


def test_directly_invoked_scripts_are_executable_in_git():
    offenders = [
        path for path in DIRECTLY_INVOKED_SCRIPTS if _git_tracked_mode(path) != "100755"
    ]
    assert offenders == [], (
        "scripts sans bit +x suivi par git (échouent en \"Permission denied\" "
        f"quand invoqués directement, ex. par cron) : {offenders}"
    )
