"""Migration Copier (exécutée au `copier update`).

⚠️ SIMULÉ. Représente la ré-application des migrations Alembic (nouvelles chaînes
de modules apportées par une évolution du template). À CONNECTER au vrai
`scripts/migrate.py` du projet généré (Chap 4/17). Voir la dette explicite.

cwd = répertoire du projet mis à jour. Copier fournit VERSION_FROM / VERSION_TO.
"""

import json
import os
from pathlib import Path


def main() -> None:
    out = Path(".gitsky")
    out.mkdir(exist_ok=True)
    (out / "updated.json").write_text(
        json.dumps(
            {
                "version_from": os.environ.get("VERSION_FROM"),
                "version_to": os.environ.get("VERSION_TO"),
                "status": "simulated",
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
