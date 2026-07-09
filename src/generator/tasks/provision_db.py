"""Task Copier — provisionne la base du projet.

⚠️ SIMULÉ. À CONNECTER au vrai PostgreSQL partagé (Chap 18) : ici on se contente
d'écrire un marqueur dans le projet généré au lieu de créer réellement la base.
Voir la dette explicite dans le plan projet.

Usage : python provision_db.py <project_name>
Exécuté par Copier avec cwd = répertoire du projet généré.
"""

import json
import sys
from pathlib import Path


def main() -> None:
    project = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    out = Path(".gitsky")
    out.mkdir(exist_ok=True)
    (out / "provisioned.json").write_text(
        json.dumps({"database": f"{project}_db", "status": "simulated"}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
