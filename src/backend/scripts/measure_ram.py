"""Mesure l'empreinte RAM du backend pour un tier donné (spike).

À lancer dans un process frais par tier pour éviter tout état d'import partagé :

    GITSKY_TIER=t0 python scripts/measure_ram.py t0
    GITSKY_TIER=t2 python scripts/measure_ram.py t2

Reporte le RSS après import de l'app (le gros de la mémoire est pris à
l'import) et quels modules ont réellement été chargés dans sys.modules.
"""

import os
import sys

import psutil


def main() -> None:
    tier = sys.argv[1] if len(sys.argv) > 1 else "t0"
    os.environ.setdefault("GITSKY_TIER", tier)

    # Import déclenche le chargement conditionnel des modules.
    import app.core.main  # noqa: F401

    proc = psutil.Process()
    rss_mb = proc.memory_info().rss / (1024 * 1024)

    print(
        f"tier={tier} "
        f"rss_mb={rss_mb:.1f} "
        f"analytics_imported={'app.modules.analytics' in sys.modules} "
        f"agentic_imported={'app.modules.agentic' in sys.modules} "
        f"security_imported={'app.modules.security' in sys.modules}"
    )


if __name__ == "__main__":
    main()
