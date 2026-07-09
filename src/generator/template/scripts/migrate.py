"""Runner de migrations multi-chaînes (équivalent Python de migrate.sh, Chap 4).

Applique **toujours** la chaîne core, puis la chaîne de chaque module activé
(flag `MODULE_*`). Chaque chaîne possède sa propre table de version, donc les
chaînes s'empilent dans la base unique du projet sans se marcher dessus.

Choix Python (vs le migrate.sh du livre) : portable (dev Windows) et testable
directement via `run_migrations()`.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import Settings, get_settings

BACKEND = Path(__file__).resolve().parents[1]
INI = BACKEND / "alembic.ini"

# section ini, dossier de la chaîne, table de version.
_CORE = ("alembic", "alembic/core", "alembic_version_core")

# flag MODULE_* -> (section, dossier, table de version).
_MODULE_CHAINS: dict[str, tuple[str, str, str]] = {
    "module_analytics": (
        "analytics",
        "alembic/modules/analytics",
        "alembic_version_analytics",
    ),
}


def _config(section: str, script_location: str, version_table: str, url: str) -> Config:
    cfg = Config(str(INI))
    cfg.config_ini_section = section
    cfg.set_main_option("script_location", str(BACKEND / script_location))
    cfg.set_main_option("version_table", version_table)
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def run_migrations(url: str | None = None, settings: Settings | None = None) -> list[str]:
    """Applique core + les chaînes des modules activés. Renvoie la liste appliquée."""
    settings = settings or get_settings()
    url = url or settings.database_url

    command.upgrade(_config(*_CORE, url), "head")
    applied = ["core"]

    for flag, (section, location, version_table) in _MODULE_CHAINS.items():
        if getattr(settings, flag):
            command.upgrade(_config(section, location, version_table, url), "head")
            applied.append(section)

    return applied


if __name__ == "__main__":
    print("Chaînes appliquées :", ", ".join(run_migrations()))
