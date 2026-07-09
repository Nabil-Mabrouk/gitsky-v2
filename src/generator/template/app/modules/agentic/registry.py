"""Registre de services agentic piloté par YAML (Chap 15).

Les services sont déclarés dans `agent_services.yaml` — on peut ajouter/modifier
un service sans toucher au code Python. Logique pure, testable.
"""

from pathlib import Path

import yaml

_CONFIG = Path(__file__).resolve().parent / "agent_services.yaml"


def load_services() -> dict:
    if not _CONFIG.is_file():
        return {}
    data = yaml.safe_load(_CONFIG.read_text(encoding="utf-8")) or {}
    return data.get("services", {})


def get_service(slug: str) -> dict | None:
    return load_services().get(slug)
