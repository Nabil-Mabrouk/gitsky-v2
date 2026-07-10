"""Task Copier — provisionne la base PostgreSQL du projet (Chap 18).

Crée une base dédiée dans l'instance PostgreSQL partagée via `docker exec`
(script provision-project-db.sh du Chap 18). Le conteneur Postgres est indiqué
par POSTGRES_CONTAINER ; sans lui (dev), l'étape est ignorée proprement.

Usage : python provision_db.py <project_name>
cwd = répertoire du projet généré.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    project = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    db_name = project.replace("-", "_")  # identifiant PostgreSQL valide
    container = os.environ.get("POSTGRES_CONTAINER", "")

    out = Path(".gitsky")
    out.mkdir(exist_ok=True)

    if not container:
        (out / "provisioned.json").write_text(
            json.dumps({"database": db_name, "status": "skipped_no_postgres"}, indent=2),
            encoding="utf-8",
        )
        return

    subprocess.run(
        ["docker", "exec", container, "createdb", "-U", "postgres", db_name],
        check=True,
    )
    (out / "provisioned.json").write_text(
        json.dumps({"database": db_name, "status": "provisioned"}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
