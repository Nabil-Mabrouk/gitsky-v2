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

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from copier_template_extensions import ContextHook

from app.core.config import MODULE_FLAGS, TIER_PROFILES


class TierResolver(ContextHook):
    def hook(self, context: dict) -> None:
        tier = context.get("gitsky_tier", "t0")
        profile = TIER_PROFILES.get(tier, {})
        # Overrides depuis config.yaml, clés courtes (agentic) sans préfixe.
        overrides = context.get("modules") or {}

        resolved: dict[str, bool] = {}
        for flag in MODULE_FLAGS:
            short = flag.removeprefix("module_")
            if short in overrides:
                resolved[flag] = bool(overrides[short])  # override gagne
            else:
                resolved[flag] = profile.get(flag, False)  # sinon profil de tier
        context["resolved_modules"] = resolved
