"""Context hook Copier — résout le tier en flags de modules.

Équivalent réel du « _pre_generation » du livre : au lieu d'un script Python
lancé avant génération (style Cookiecutter), Copier expose un *context hook* qui
enrichit le contexte Jinja avant le rendu des fichiers.

Les profils de tier sont VENDORISÉS (copie autonome de `app.core.config`) car le
template génère depuis un checkout git où `src/backend` n'est pas importable. La
synchro générateur↔runtime est garantie par un test (test_generator_tiers_match_backend).
"""

import yaml

from copier_template_extensions import ContextHook

MODULE_FLAGS: tuple[str, ...] = (
    "module_auth",
    "module_admin",
    "module_analytics",
    "module_onboarding",
    "module_tutorials",
    "module_security_middleware",
    "module_i18n",
    "module_agentic",
    "module_monetization_shop",
    "module_monetization_subscription",
)

TIER_PROFILES: dict[str, dict[str, bool]] = {
    "t0": {flag: False for flag in MODULE_FLAGS},
    "t1": {
        "module_auth": True,
        "module_analytics": True,
        "module_security_middleware": True,
    },
    "t2": {
        "module_auth": True,
        "module_admin": True,
        "module_analytics": True,
        "module_onboarding": True,
        "module_security_middleware": True,
        "module_i18n": True,
        "module_agentic": True,
        "module_monetization_shop": True,
        "module_monetization_subscription": True,
    },
}

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
        # Dérive les valeurs plates depuis le bloc imbriqué `project` du livre.
        project = _as_obj(context.get("project"), {}) or {}
        project_name = project.get("name", "mon-projet")
        tier = project.get("tier", "t0")
        context["project_name"] = project_name
        context["gitsky_tier"] = tier
        context["project_domain"] = (
            project.get("domain") or f"{project_name}.mystudio.com"
        )

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

        # Branding : garantit les 3 clés même si le branding fourni est partiel.
        branding = _as_obj(context.get("branding"), {})
        context["branding"] = {
            "primary_color": "#4F46E5",
            "primary_foreground": "#FFFFFF",
            "font_family": "Inter",
            **(branding or {}),
        }
