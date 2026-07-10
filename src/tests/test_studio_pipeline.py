"""Pipeline Studio (Phase 5, incrément 5) — logique testée (LLM stubbé).

Vérifie la production d'un Creative Manifest valide + trace + verdict guardrails,
le déterminisme du stub, le choix de skin par verticale, et le rendu bout-en-bout
(manifest -> vitrine). Pas la qualité créative (hors scope test, demande de l'éval).
"""

import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

SRC = Path(__file__).resolve().parents[1]
VITRINE = SRC / "generator" / "template" / "vitrine"
sys.path.insert(0, str(SRC / "shared_services"))

from studio.guardrails import contrast_ratio  # noqa: E402
from studio.inputs import HarvestPacket  # noqa: E402
from studio.manifest import to_copier_data  # noqa: E402
from studio.pipeline import run  # noqa: E402


def _packet(**kw) -> HarvestPacket:
    base = {"project": "pain-scraper", "idea_oneliner": "Collecte les signaux de douleur", "audience": "devs", "vertical": "dev-tools"}
    base.update(kw)
    return HarvestPacket(**base)


def test_pipeline_produces_valid_manifest_and_trace():
    result = run(_packet())
    m, trace, verdict = result.manifest, result.trace, result.verdict

    assert m.project == "pain-scraper"
    assert m.brief.skin in ("clean", "editorial", "bold")
    assert m.brief.palette  # non vide
    assert m.brief.rationale  # auditabilité
    assert any(b.type == "hero" for b in m.blocks)
    assert m.provenance.inputs_hash

    # Trace immuable et complète (5 étapes : 4 agents + qa).
    assert [s.agent for s in trace.steps] == ["art_director", "copywriter", "media", "assembler", "qa"]
    assert trace.inputs_hash == m.provenance.inputs_hash

    # Guardrails déterministes : palettes curées sombre-sur-blanc -> a11y OK.
    assert verdict["pass"] is True


def test_stub_pipeline_is_deterministic():
    p = _packet(project="x", vertical="v", audience="a")
    r1, r2 = run(p), run(p)
    assert r1.manifest.brief.model_dump() == r2.manifest.brief.model_dump()
    assert [b.model_dump() for b in r1.manifest.blocks] == [b.model_dump() for b in r2.manifest.blocks]
    # ... mais le run_id (provenance) diffère à chaque run.
    assert r1.manifest.provenance.run_id != r2.manifest.provenance.run_id


def test_skin_chosen_by_vertical():
    assert run(_packet(vertical="media publishing")).manifest.brief.skin == "editorial"
    assert run(_packet(vertical="consumer gaming")).manifest.brief.skin == "bold"
    assert run(_packet(vertical="dev-tools", audience="devs")).manifest.brief.skin == "clean"


def test_contrast_ratio_wcag():
    assert contrast_ratio("#000000", "#FFFFFF") > 20  # noir/blanc ≈ 21
    assert contrast_ratio("#777777", "#FFFFFF") < 4.5  # gris moyen sur blanc


def test_manifest_renders_to_vitrine_end_to_end():
    m = run(_packet(idea_oneliner="Marre du scraping ?")).manifest
    data = to_copier_data(m)
    env = Environment(loader=FileSystemLoader(str(VITRINE)))
    html = env.get_template("landing.html.jinja").render(
        project_name=m.project, branding=data["branding"], landing=data["landing"]
    )
    assert "Marre du scraping ?" in html  # le copy du pipeline pilote la vitrine
    assert data["branding"]["primary_color"] in html  # le brief pilote la palette
