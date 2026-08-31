"""MODULES.md.jinja — guide par module actif (Chap 2/9/12/15/16), généré à
chaque projet pour que le développeur qui personnalise le repo sache où
étendre en sécurité et ce qui est châssis (réécrit par `copier update`).
Ne liste que les modules réellement actifs — pas de bruit pour les autres.
"""

from helpers import projet_genere  # noqa: E402


def _modules_md(**modules) -> str:
    with projet_genere("pain-scraper", modules=modules) as dst:
        return (dst / "MODULES.md").read_text(encoding="utf-8")


def test_no_active_modules_shows_fallback_message_only():
    body = _modules_md()
    assert "Aucun module optionnel n'est actif" in body
    # Aucune section de module ne doit apparaître.
    for heading in ("## Admin", "## Framework agentic", "## Fleet", "## Worker", "## Leads"):
        assert heading not in body


def test_only_active_modules_get_a_section():
    body = _modules_md(admin=True, agentic=True)
    assert "## Admin (`MODULE_ADMIN`)" in body
    assert "## Framework agentic (`MODULE_AGENTIC`)" in body
    # Modules non activés : aucune section, aucun bruit.
    for heading in (
        "## Internationalisation",
        "## Analytics",
        "## Onboarding",
        "## Contenu / Tutoriaux",
        "## SecurityMiddleware",
        "## Monétisation",
        "## Fleet",
        "## Worker",
        "## Leads",
    ):
        assert heading not in body


def test_admin_section_points_to_app_domain_not_itself():
    body = _modules_md(admin=True)
    assert "aucun point d'extension dans ce module" in body
    assert "app/domain/routers.py" in body


def test_onboarding_section_documents_the_real_extension_point():
    body = _modules_md(onboarding=True)
    assert "flows/<id>.json" in body
    assert "engine.py" in body


def test_agentic_section_documents_both_extension_points():
    body = _modules_md(agentic=True)
    assert "agent_services.yaml" in body
    assert "tools/__init__.py" in body
    assert "TOOLS" in body


def test_monetization_heading_combines_shop_and_subscription():
    shop_only = _modules_md(monetization_shop=True)
    assert "## Monétisation (boutique)" in shop_only

    both = _modules_md(monetization_shop=True, monetization_subscription=True)
    assert "## Monétisation (boutique + abonnements)" in both


def test_fleet_section_warns_it_is_dashboard_only():
    body = _modules_md(fleet=True)
    assert "## Fleet (`MODULE_FLEET`)" in body
    assert "jamais pour un projet métier ordinaire" in body


def test_worker_section_documents_the_extension_point():
    body = _modules_md(worker=True)
    assert "## Worker (`MODULE_WORKER`)" in body
    assert "app/domain/worker_cycle.py" in body
    assert "run_cycle(db, stop_requested)" in body


def test_leads_section_documents_no_extension_point():
    body = _modules_md(leads=True)
    assert "## Leads (`MODULE_LEADS`)" in body
    assert "aucun point d'extension" in body
    assert "LEADS_COLLECTOR_TOKEN" in body


def test_readme_links_to_modules_md():
    with projet_genere("pain-scraper") as dst:
        readme = (dst / "README.md").read_text(encoding="utf-8")
    assert "[`MODULES.md`](MODULES.md)" in readme
