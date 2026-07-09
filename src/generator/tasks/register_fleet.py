"""Task Copier — enregistre le projet auprès du fleet dashboard.

⚠️ SIMULÉ. À CONNECTER à l'API réelle du fleet dashboard (Chap 19) : ici on écrit
un marqueur au lieu de POSTer sur l'API. Voir la dette explicite dans le plan.

Usage : python register_fleet.py <project_name> <tier>
Exécuté par Copier avec cwd = répertoire du projet généré.
"""

import json
import sys
from pathlib import Path


def main() -> None:
    project = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    tier = sys.argv[2] if len(sys.argv) > 2 else "t0"
    out = Path(".gitsky")
    out.mkdir(exist_ok=True)
    (out / "fleet.json").write_text(
        json.dumps(
            {"project": project, "tier": tier, "registered": "simulated"}, indent=2
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
