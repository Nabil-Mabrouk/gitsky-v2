"""Task Copier — enregistre le projet auprès du fleet dashboard (Chap 19).

Appelle réellement `POST {FLEET_URL}/api/fleet/projects/register`. Sans FLEET_URL
(dev), l'inscription est ignorée proprement. Un projet « n'existe » dans la flotte
que s'il est enregistré ici.

Usage : python register_fleet.py <project_name> <tier>
cwd = répertoire du projet généré. FLEET_URL / PROJECT_DOMAIN via l'environnement.
"""

import json
import os
import sys
from pathlib import Path

import httpx


def register(
    project: str,
    tier: str,
    domain: str,
    template_version: str,
    fleet_url: str,
    client: httpx.Client | None = None,
) -> None:
    payload = {
        "name": project,
        "tier": tier,
        "domain": domain,
        "template_version": template_version,
    }
    out = Path(".gitsky")
    out.mkdir(exist_ok=True)

    if not fleet_url:
        (out / "fleet.json").write_text(
            json.dumps({**payload, "registered": "skipped_no_fleet_url"}, indent=2),
            encoding="utf-8",
        )
        return

    http = client or httpx.Client(timeout=10)
    response = http.post(
        f"{fleet_url.rstrip('/')}/api/fleet/projects/register", json=payload
    )
    response.raise_for_status()
    (out / "fleet.json").write_text(
        json.dumps(
            {**payload, "registered": "ok", "fleet_status": response.status_code},
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    register(
        project=sys.argv[1] if len(sys.argv) > 1 else "unknown",
        tier=sys.argv[2] if len(sys.argv) > 2 else "t0",
        domain=os.environ.get("PROJECT_DOMAIN", ""),
        template_version=os.environ.get("VERSION_TO", ""),
        fleet_url=os.environ.get("FLEET_URL", ""),
    )


if __name__ == "__main__":
    main()
