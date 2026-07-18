"""Configuration centralisée (Phase 1).

`GITSKY_TIER` fixe le profil par défaut des flags `MODULE_*` (tableau Chap 2 §3),
chaque flag pouvant être surchargé individuellement par une variable
d'environnement (Chap 3 §Config).

Sémantique de surcharge :
- flag absent de l'env   -> None -> valeur du profil de tier
- flag présent dans l'env -> True/False explicite (gagne toujours)

Note SEO : le SEO dynamique est présent à tous les tiers (Chap 2) — il fait
partie du core, ce n'est donc pas un flag `MODULE_*`.
"""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Liste canonique des modules optionnels (Chap 3 §config.py).
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
    "module_fleet",
)

# Profils par défaut par tier, dérivés du tableau Chap 2 §3.
# Un flag absent d'un profil vaut False par défaut.
# - T0 : « via collector/proxy partagé » = module LOCAL désactivé.
# - T1 : agentic « optionnel » -> False par défaut (surcharge projet possible).
# - T2 : tutorials « selon projet » -> False par défaut (surcharge projet).
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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    project_name: str = "gitsky-spike"
    # Placeholder DEV uniquement — ≥ 32 octets (RFC 7518 pour HS256).
    # La prod DOIT fournir une vraie clé secrète via l'environnement.
    secret_key: str = "dev-insecure-change-me-in-production-0123456789"
    frontend_url: str = "http://localhost:5173"
    environment: str = "development"
    gitsky_tier: str = "t0"

    # SEO (Chap 10, core à tous les tiers). `site_url` est l'origine publique
    # canonique du projet (https://mon-projet.com) — sert de préfixe absolu aux
    # URLs du sitemap et à la ligne Sitemap: de robots.txt. En dev on retombe
    # sur frontend_url ; la prod fournit le vrai domaine via l'environnement.
    site_url: str = "http://localhost:5173"
    # Langues indexées, la première étant la langue par défaut (sans préfixe
    # d'URL). Le sitemap n'émet des alternates hreflang que si module_i18n est
    # actif ET qu'au moins deux langues sont déclarées (Chap 10 §i18n).
    supported_languages: list[str] = ["fr"]

    # SQLAlchemy async. Défaut SQLite local pour le dev ; la prod fournit une
    # URL PostgreSQL asyncpg (postgresql+asyncpg://...) via l'environnement.
    database_url: str = "sqlite+aiosqlite:///./gitsky.db"

    # Auth / JWT (Chap 7). Access court en localStorage, refresh long en cookie.
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # None = « non spécifié » -> rempli par le profil de tier.
    module_auth: bool | None = None
    module_admin: bool | None = None
    module_analytics: bool | None = None
    module_onboarding: bool | None = None
    module_tutorials: bool | None = None
    module_security_middleware: bool | None = None
    module_i18n: bool | None = None
    module_agentic: bool | None = None
    module_monetization_shop: bool | None = None
    module_monetization_subscription: bool | None = None
    # Module spécial : activé uniquement pour l'app fleet dashboard (mystudio.com).
    module_fleet: bool | None = None

    @model_validator(mode="after")
    def apply_tier_defaults(self) -> "Settings":
        profile = TIER_PROFILES.get(self.gitsky_tier, {})
        for flag in MODULE_FLAGS:
            if getattr(self, flag) is None:
                setattr(self, flag, profile.get(flag, False))
        return self

    @property
    def enabled_modules(self) -> list[str]:
        """Modules actifs, sans le préfixe `module_` — pratique pour logs/health."""
        return [
            flag.removeprefix("module_")
            for flag in MODULE_FLAGS
            if getattr(self, flag)
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
