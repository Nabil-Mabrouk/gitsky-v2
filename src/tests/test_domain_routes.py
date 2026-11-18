"""Point d'extension frontend des pages métier (bug réel 0-hl, 2026-11-18).

App.tsx est châssis : sans frontend/src/domain/routes.tsx, chaque projet
éditait App.tsx à la main (politique-ia 27 routes, f-ynd 44, ai-qube 47) et
héritait d'un conflit, ou d'une fusion silencieuse, à chaque copier update.
"""

import tempfile
from pathlib import Path

from copier import run_copy, run_update

from helpers import projet_genere  # noqa: E402
from test_studio_spike import _git, _make_versioned_template, _rmtree_robuste  # noqa: E402

ROUTES = Path("frontend") / "src" / "domain" / "routes.tsx"


def test_domain_routes_file_is_generated_and_wired_into_app():
    with projet_genere("zero-hl") as dst:
        routes = (dst / ROUTES).read_text(encoding="utf-8")
        app = (dst / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    # Contrat fixé avec 0-hl (ADR-015), qui a déjà son propre routes.tsx :
    # le nom de l'export ne doit pas changer, sinon App.tsx casse chez lui.
    assert "export const domainRoutes" in routes
    assert 'import { domainRoutes } from "./domain/routes"' in app


def test_domain_routes_preserved_on_copier_update():
    root = Path(tempfile.mkdtemp())
    try:
        template = root / "template"
        _make_versioned_template(template)

        project = root / "project"
        run_copy(
            str(template),
            str(project),
            data={"project": {"name": "x"}},
            defaults=True,
            quiet=True,
            unsafe=True,
        )
        routes_path = project / ROUTES
        assert routes_path.exists()

        routes_path.write_text("// ROUTES DU PROJET\n", encoding="utf-8")
        _git(project, "config", "core.autocrlf", "false")
        _git(project, "config", "user.email", "t@t")
        _git(project, "config", "user.name", "t")
        _git(project, "add", "-A")
        _git(project, "commit", "-q", "-m", "routes metier")

        (template / "template" / ROUTES).write_text("// NOUVELLE VERSION TEMPLATE\n", encoding="utf-8")
        _git(template, "add", "-A")
        _git(template, "commit", "-q", "-m", "v1.0.0")
        _git(template, "tag", "v1.0.0")

        run_update(str(project), defaults=True, overwrite=True, quiet=True, unsafe=True)

        content = routes_path.read_text("utf-8")
        assert "ROUTES DU PROJET" in content
        assert "NOUVELLE VERSION TEMPLATE" not in content
    finally:
        _rmtree_robuste(root)
