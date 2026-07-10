"""Migration Copier (exécutée au `copier update`).

Ré-applique les migrations du projet (core + chaînes des modules activés) en
lançant son propre runner `scripts/migrate.py`. C'est ce qui propage les
nouvelles chaînes Alembic apportées par une évolution du template.

cwd = répertoire du projet mis à jour. Copier fournit VERSION_FROM / VERSION_TO.
Écrit un marqueur d'observabilité `.gitsky/updated.json`.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.migrate"],
        cwd=".",
        env={**os.environ, "PYTHONPATH": "."},
        capture_output=True,
        text=True,
    )

    out = Path(".gitsky")
    out.mkdir(exist_ok=True)
    (out / "updated.json").write_text(
        json.dumps(
            {
                "version_from": os.environ.get("VERSION_FROM"),
                "version_to": os.environ.get("VERSION_TO"),
                "migrate_returncode": result.returncode,
                "status": "applied" if result.returncode == 0 else "failed",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    # Remonte l'échec pour que copier update signale le problème.
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
