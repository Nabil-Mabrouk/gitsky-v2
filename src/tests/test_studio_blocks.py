"""Catalogue de blocs de la vitrine (Chap 24 — landing React).

Le rendu HTML par type de bloc (layouts hero/features/testimonial/faq,
contraste WCAG, comportement du fetch /leads) a MIGRÉ vers les tests React
(frontend/src/pages/Landing.test.tsx, frontend/src/components/blocks/*.test.tsx)
depuis que T0 rend la landing via l'app React partagée avec T1/T2 plutôt que
via Jinja. Ce module ne vérifie plus que ce dont Jinja reste responsable :
`landing-manifest.json.jinja` sérialise fidèlement le schéma de blocs produit
par Studio en JSON valide, sans en altérer le contenu.
"""

import json
import os
import shutil
import stat
import tempfile
import time
from pathlib import Path

from copier import run_copy

SRC = Path(__file__).resolve().parents[1]
GENERATOR = SRC / "generator"


def _rmtree_robuste(path: Path) -> None:
    # Sous Windows, un .git contient des objets en lecture seule ET un handle
    # peut rester brièvement ouvert (processus git qui vient de sortir,
    # antivirus). On rend inscriptible, puis on réessaie le retrait complet
    # avec un court backoff tant que le verrou transitoire n'est pas relâché.
    def _onexc(func, p, exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    for essai in range(5):
        try:
            shutil.rmtree(path, onexc=_onexc)
            return
        except (PermissionError, OSError):
            if essai == 4:
                raise
            time.sleep(0.2 * (essai + 1))


def _generate_manifest(landing: dict, project: dict | None = None) -> dict:
    root = Path(tempfile.mkdtemp())
    try:
        dst = root / "proj"
        run_copy(
            str(GENERATOR),
            str(dst),
            data={"project": project or {"name": "acme"}, "landing": landing},
            defaults=True,
            quiet=True,
            unsafe=True,
        )
        return json.loads((dst / "frontend" / "src" / "landing-manifest.json").read_text("utf-8"))
    finally:
        _rmtree_robuste(root)


FULL_LANDING = {
    "skin": "editorial",
    "hero_image": "data:image/png;base64,AAAA",
    "blocks": [
        {
            "type": "hero",
            "layout": "split",
            "headline": "Titre Hero",
            "subhead": "Sous-titre",
            "badge": "Nouveau",
            "cta_primary": {"label": "Voir plus", "target": "#features"},
        },
        {
            "type": "features",
            "layout": "grid",
            "headline": "Fonctions",
            "items": [{"title": "Rapide", "description": "Très rapide"}],
        },
        {"type": "testimonial", "layout": "card", "quote": "Produit génial", "attribution": "Alice"},
        {
            "type": "faq",
            "layout": "accordion",
            "headline": "FAQ",
            "items": [{"question": "Comment ?", "answer": "Comme ça"}],
        },
        {"type": "pricing", "headline": "Tarifs", "plans": [{"name": "Pro", "price": "29€", "features": ["X", "Y"]}]},
        {
            "type": "email_capture",
            "headline": "Rejoignez",
            "subhead": "Un email, rien d'autre",
            "cta": "S'inscrire",
            "legal_note": "Désinscription en un clic",
        },
    ],
}


def test_manifest_serializes_project_identity_and_skin():
    manifest = _generate_manifest(FULL_LANDING)
    assert manifest["project"] == "acme"
    # Double opt-in (Chap 18) : le domaine du projet est injecté pour que
    # landing-collector puisse construire le lien de confirmation — défaut
    # {name}.mystudio.com quand aucun domaine explicite n'est fourni.
    assert manifest["domain"] == "acme.mystudio.com"
    assert manifest["skin"] == "editorial"
    assert manifest["hero_image"] == "data:image/png;base64,AAAA"


def test_manifest_preserves_all_block_fields_verbatim():
    manifest = _generate_manifest(FULL_LANDING)
    assert manifest["blocks"] == FULL_LANDING["blocks"]


def test_manifest_hero_image_defaults_to_empty_string_when_absent():
    # landing.hero_image n'existe pas dans le schéma par défaut de copier.yml
    # (seul to_copier_data() en produit un) — le template le protège d'un
    # Undefined Jinja avec `(landing.hero_image or "")`.
    manifest = _generate_manifest({"blocks": [{"type": "hero", "headline": "H"}]})
    assert manifest["hero_image"] == ""


def test_manifest_is_valid_json_even_with_unicode_and_quotes():
    manifest = _generate_manifest(
        {"blocks": [{"type": "hero", "headline": 'Guillemets "et" accents éàç'}]}
    )
    assert manifest["blocks"][0]["headline"] == 'Guillemets "et" accents éàç'
