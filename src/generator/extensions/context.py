"""Context hook Copier — résout le tier en flags de modules.

Équivalent réel du « _pre_generation » du livre : au lieu d'un script Python
lancé avant génération (style Cookiecutter), Copier expose un *context hook* qui
enrichit le contexte Jinja avant le rendu des fichiers.

Source unique de vérité : on réutilise `TIER_PROFILES` / `MODULE_FLAGS` de
`app.core.config` — le générateur et le runtime résolvent le tier de façon
identique. (En packaging réel, le backend serait vendorisé ou installé ; ici le
spike ajoute src/backend au sys.path.)
"""

import sys
from pathlib import Path

import yaml

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from copier_template_extensions import ContextHook

from app.core.config import MODULE_FLAGS, TIER_PROFILES

# Types config.yaml -> expression de colonne SQLAlchemy.
_SA_TYPES: dict[str, str] = {
    "str": "String",
    "text": "Text",
    "int": "Integer",
    "bool": "Boolean",
    "float": "Float",
    "datetime": "DateTime(timezone=True)",
}


def _as_obj(value, default):
    """Normalise une réponse Copier en objet Python.

    Via `--data-file config.yaml`, Copier fournit déjà des listes/dicts. Via
    `--data key=...`, la valeur arrive comme chaîne : on la parse en YAML.
    """
    if value is None or value == "":
        return default
    if isinstance(value, str):
        return yaml.safe_load(value) or default
    return value


def _pluralize(name: str) -> str:
    """Nom de table à partir du nom de modèle (Company -> companies)."""
    lower = name.lower()
    if lower.endswith("y") and (len(lower) < 2 or lower[-2] not in "aeiou"):
        return lower[:-1] + "ies"
    if lower.endswith(("s", "x", "z", "ch", "sh")):
        return lower + "es"
    return lower + "s"


def _resolve_domain_models(data_models: list) -> list:
    """Enrichit chaque modèle avec son nom de table et ses colonnes SQLAlchemy."""
    resolved = []
    for model in data_models:
        fields = [
            {"name": fname, "column": _SA_TYPES.get(ftype, "String")}
            for fname, ftype in (model.get("fields") or {}).items()
        ]
        resolved.append(
            {
                "name": model["name"],
                "table": _pluralize(model["name"]),
                "fields": fields,
            }
        )
    return resolved


class TierResolver(ContextHook):
    def hook(self, context: dict) -> None:
        tier = context.get("gitsky_tier", "t0")
        profile = TIER_PROFILES.get(tier, {})
        # Overrides depuis config.yaml, clés courtes (agentic) sans préfixe.
        overrides = _as_obj(context.get("modules"), {})

        resolved: dict[str, bool] = {}
        for flag in MODULE_FLAGS:
            short = flag.removeprefix("module_")
            if short in overrides:
                resolved[flag] = bool(overrides[short])  # override gagne
            else:
                resolved[flag] = profile.get(flag, False)  # sinon profil de tier
        context["resolved_modules"] = resolved

        # Scaffolding métier : app/domain/ depuis data_models.
        context["domain_models"] = _resolve_domain_models(
            _as_obj(context.get("data_models"), [])
        )
