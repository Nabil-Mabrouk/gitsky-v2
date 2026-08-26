"""Contrat d'autorisation des routes (durcissement — garde-fou systémique).

Le trou fleet (`/projects/register` public) et l'IDOR agentic ont montré que la
sécurité route-par-route ne survit pas aux ajouts futurs sans garde-fou global.
Ce test monte l'app COMPLÈTE (tous les flags MODULE_* actifs) et vérifie, pour
chaque route réellement enregistrée :

1. tout ce qui vit sous /api/admin/ exige `require_admin` ;
2. toute route mutante (POST/PUT/PATCH/DELETE) porte une dépendance d'auth —
   sauf si elle figure dans l'allowlist EXPLICITE ci-dessous, qui documente
   pourquoi elle est volontairement publique.

Ajouter une route mutante sans auth fait échouer la CI : c'est voulu. Si la
route est légitimement publique, l'ajouter à l'allowlist AVEC sa justification.

Sous-process (patron de test_conditional_loading) : `app.core.main` fige ses
flags à l'import, un process frais garantit la combinaison de flags voulue.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"

# Dépendances reconnues comme « auth » : leur présence prouve que l'accès est
# contrôlé (l'optionnelle compte — c'est un choix conscient d'accès mixte).
AUTH_DEPS = {
    "require_admin",
    "get_current_user",
    "get_current_user_optional",
    "verify_fleet_service_token",
}

# Routes mutantes VOLONTAIREMENT publiques : (méthode, chemin) -> justification.
PUBLIC_MUTATING_ALLOWLIST = {
    ("POST", "/api/auth/register"): "création de compte : pas encore de session",
    ("POST", "/api/auth/accept-invite"): "activation d'un compte waitlist : pas encore de session, sécurisé par le jeton d'invitation lui-même",
    ("POST", "/api/auth/login"): "ouverture de session : pas encore de token",
    ("POST", "/api/auth/refresh"): "auth par cookie HttpOnly, pas par Bearer",
    ("POST", "/api/auth/logout"): "doit fonctionner même avec un token expiré",
    ("POST", "/api/shop/webhook"): "appelé par Stripe, authentifié par signature",
    ("POST", "/api/onboarding/evaluate"): "scoring public sans persistance (Chap 12)",
}

SNIPPET = r"""
import json
from fastapi.routing import APIRoute
from app.core.main import app

def dep_names(route):
    names, stack = set(), list(route.dependant.dependencies)
    while stack:
        d = stack.pop()
        names.add(getattr(d.call, "__name__", repr(d.call)))
        stack.extend(d.dependencies)
    return sorted(names)

def collect(routes, prefix=""):
    # FastAPI >= 0.130 : include_router est paresseux (_IncludedRouter) —
    # app.routes n'aplatit plus les routeurs inclus, on les déplie nous-mêmes.
    for r in routes:
        if isinstance(r, APIRoute):
            yield prefix + r.path, r
        elif hasattr(r, "include_context"):
            ctx = r.include_context
            yield from collect(r.original_router.routes, prefix + (ctx.prefix or ""))

routes = [
    {"path": path, "methods": sorted(r.methods - {"HEAD", "OPTIONS"}), "deps": dep_names(r)}
    for path, r in collect(app.routes)
]
print(json.dumps(routes))
"""


def _all_routes() -> list[dict]:
    env = {
        **os.environ,
        "MODULE_ADMIN": "true",
        "MODULE_ANALYTICS": "true",
        "MODULE_ONBOARDING": "true",
        "MODULE_TUTORIALS": "true",
        "MODULE_SECURITY_MIDDLEWARE": "true",
        "MODULE_I18N": "true",
        "MODULE_AGENTIC": "true",
        "MODULE_MONETIZATION_SHOP": "true",
        "MODULE_MONETIZATION_SUBSCRIPTION": "true",
        "MODULE_FLEET": "true",
        "PYTHONPATH": str(BACKEND),
    }
    out = subprocess.check_output(
        [sys.executable, "-c", SNIPPET], cwd=str(BACKEND), env=env, text=True
    )
    return json.loads(out.strip().splitlines()[-1])


ROUTES = _all_routes()


def test_the_full_catalog_is_actually_mounted():
    # Le contrat ne vaut que s'il inspecte la vraie surface : un échantillon
    # de chaque famille doit être présent.
    paths = {r["path"] for r in ROUTES}
    for expected in (
        "/api/auth/login",
        "/api/admin/analytics/world",
        "/api/agent-services/executions/{execution_id}",
        "/api/fleet/projects/register",
        "/api/shop/webhook",
        "/api/content/tutorials",
    ):
        assert expected in paths, f"route témoin absente : {expected}"


def test_admin_routes_all_require_admin():
    offenders = [
        (r["methods"], r["path"])
        for r in ROUTES
        if r["path"].startswith("/api/admin/") and "require_admin" not in r["deps"]
    ]
    assert offenders == [], f"routes /api/admin/* sans require_admin : {offenders}"


def test_mutating_routes_require_auth_or_explicit_allowlist():
    offenders = []
    for r in ROUTES:
        for method in r["methods"]:
            if method not in ("POST", "PUT", "PATCH", "DELETE"):
                continue
            if (method, r["path"]) in PUBLIC_MUTATING_ALLOWLIST:
                continue
            if not AUTH_DEPS & set(r["deps"]):
                offenders.append((method, r["path"], r["deps"]))
    assert offenders == [], (
        "routes mutantes sans auth ni allowlist (ajouter une dépendance d'auth, "
        f"ou documenter dans PUBLIC_MUTATING_ALLOWLIST) : {offenders}"
    )


def test_allowlist_contains_no_dead_entries():
    # Une entrée d'allowlist qui ne correspond plus à aucune route est un
    # résidu : on la retire pour garder le contrat honnête.
    live = {(m, r["path"]) for r in ROUTES for m in r["methods"]}
    dead = [entry for entry in PUBLIC_MUTATING_ALLOWLIST if entry not in live]
    assert dead == [], f"entrées d'allowlist obsolètes : {dead}"
