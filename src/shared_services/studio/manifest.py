"""Creative Manifest — le contrat Studio ↔ générateur (Chap 24).

Sortie GELÉE et VERSIONNÉE du Studio. `to_copier_data` le projette en données
copier (`branding` + `landing`) de façon déterministe : deux générations depuis
le même manifest produisent une vitrine identique — condition du cycle
kill → résurrection (Chap 20).
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Brief(BaseModel):
    skin: str = "default"
    palette: dict[str, str] = Field(default_factory=dict)  # primary, primary_foreground...
    type_pairing: dict[str, str] = Field(default_factory=dict)  # display, body
    tone: str = ""
    rationale: str = ""  # pourquoi ce parti-pris (auditabilité)


class Block(BaseModel):
    # extra="allow" : champs spécifiques au type (headline, items, plans...).
    model_config = ConfigDict(extra="allow")
    type: str


class MediaAsset(BaseModel):
    id: str
    kind: str = "image"  # image | video
    prompt: str = ""
    asset_ref: str = ""
    license: str = "generated-owned"


class Provenance(BaseModel):
    run_id: str = ""
    generated_by: str = ""  # modèle
    prompt_template: str = ""  # ex. art_director@v3
    inputs_hash: str = ""


class CreativeManifest(BaseModel):
    manifest_version: int = 1
    project: str
    brief: Brief
    blocks: list[Block] = Field(default_factory=list)
    media: list[MediaAsset] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)


def to_copier_data(manifest: CreativeManifest) -> dict:
    """Projette le manifest en données copier (branding + landing)."""
    palette = manifest.brief.palette
    typo = manifest.brief.type_pairing
    return {
        "branding": {
            "primary_color": palette.get("primary", "#4F46E5"),
            "primary_foreground": palette.get("primary_foreground", "#FFFFFF"),
            "font_family": typo.get("body", "Inter"),
        },
        "landing": {"blocks": [b.model_dump() for b in manifest.blocks]},
    }


# --- Stockage versionné (startup-factory-configs/manifests/<project>.yaml) ---

def _manifest_path(project: str, base_dir: Path) -> Path:
    return base_dir / "manifests" / f"{project}.yaml"


def save_manifest(manifest: CreativeManifest, base_dir: Path) -> Path:
    """Écrit le manifest. Si une version existe déjà, incrémente manifest_version."""
    path = _manifest_path(manifest.project, base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        existing = load_manifest(manifest.project, base_dir)
        manifest.manifest_version = existing.manifest_version + 1
    path.write_text(
        yaml.safe_dump(manifest.model_dump(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def load_manifest(project: str, base_dir: Path) -> CreativeManifest:
    path = _manifest_path(project, base_dir)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return CreativeManifest.model_validate(data)
