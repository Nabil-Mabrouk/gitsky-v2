"""AGENTS.md.jinja / CLAUDE.md.jinja — guide de personnalisation généré à
chaque projet (Chap 24, round layout). Contrairement à MODULES.md.jinja,
inconditionnel : le cycle de vie/la frontière châssis-personnalisable
qu'ils documentent s'applique à tout projet, pas seulement selon les
modules actifs.
"""

from helpers import projet_genere  # noqa: E402


def test_agents_md_generated_for_every_project_no_modules():
    with projet_genere("pain-scraper") as dst:
        body = (dst / "AGENTS.md").read_text(encoding="utf-8")
    assert "pain-scraper" in body
    assert "app/domain/" in body


def test_agents_md_generated_with_modules_active_too():
    with projet_genere("pain-scraper", modules={"admin": True, "fleet": True}) as dst:
        body = (dst / "AGENTS.md").read_text(encoding="utf-8")
    assert "pain-scraper" in body


def test_agents_md_documents_the_customization_boundary():
    with projet_genere("pain-scraper") as dst:
        body = (dst / "AGENTS.md").read_text(encoding="utf-8")
    # À vous.
    assert "components/layout/Navbar.tsx" in body
    assert "components/layout/Footer.tsx" in body
    assert "app/domain/models.py" in body
    # Ne jamais toucher directement — le contrat avec le fleet dashboard.
    assert "GET /health" in body
    assert "docker-compose.yml" in body
    assert ".env.local" in body
    # Vérifications avant commit/push.
    assert "npm run typecheck" in body
    assert "npm run test" in body
    assert "npm run build" in body


def test_claude_md_points_to_agents_and_modules():
    with projet_genere("pain-scraper") as dst:
        body = (dst / "CLAUDE.md").read_text(encoding="utf-8")
    assert "[`AGENTS.md`](AGENTS.md)" in body
    assert "[`MODULES.md`](MODULES.md)" in body


def test_readme_links_to_agents_and_claude_md():
    with projet_genere("pain-scraper") as dst:
        readme = (dst / "README.md").read_text(encoding="utf-8")
    assert "[`AGENTS.md`](AGENTS.md)" in readme
    assert "[`CLAUDE.md`](CLAUDE.md)" in readme


def test_branding_local_css_generated_and_imported_after_theme():
    # Round theming (Chap 24) : point d'extension pour personnaliser la
    # marque après génération, sans toucher theme.css (régénéré par
    # copier update depuis le branding du Studio).
    with projet_genere("pain-scraper") as dst:
        assert (dst / "frontend/src/branding.local.css").exists()
        index_css = (dst / "frontend/src/index.css").read_text(encoding="utf-8")
    theme_pos = index_css.index("./theme.css")
    branding_pos = index_css.index("./branding.local.css")
    assert theme_pos < branding_pos


def test_agents_md_documents_llm_proxy_contract():
    # Round 2026-11-21 : l'agent de 0-hl a dû poser 9 questions pour savoir
    # comment appeler le proxy LLM — le contrat n'était documenté nulle part
    # dans le projet généré.
    with projet_genere("pain-scraper") as dst:
        body = (dst / "AGENTS.md").read_text(encoding="utf-8")
    assert "LLM_PROXY_URL=http://llm-proxy:4000" in body
    assert "LLM_PROXY_TOKEN" in body
    assert "llm-proxy-keys.sh create-key" in body
    assert "/v1/models" in body
    assert "/key/info" in body
    assert "budget_exceeded" in body
    assert "llm_client.py" in body  # ne renvoie que du texte, pas les tool_calls


def test_env_local_example_has_llm_vars_only_with_agentic():
    with projet_genere("pain-scraper", modules={"agentic": True}) as dst:
        agentic = (dst / ".env.local.example").read_text(encoding="utf-8")
    with projet_genere("pain-scraper") as dst:
        plain = (dst / ".env.local.example").read_text(encoding="utf-8")
    assert "LLM_PROXY_URL=http://llm-proxy:4000" in agentic
    assert "LLM_PROXY_TOKEN=" in agentic
    assert "LLM_PROXY_TOKEN" not in plain
