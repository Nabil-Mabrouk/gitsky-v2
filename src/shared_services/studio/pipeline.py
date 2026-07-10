"""Orchestrateur du pipeline Studio (Chap 24).

Enchaîne les agents (DA → rédacteur → média → assembleur) puis la QA guardrails,
et produit un Creative Manifest GELÉ + une StudioTrace immuable (auditabilité).
"""

import hashlib
import json
import uuid
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from studio import agents, guardrails
from studio.inputs import HarvestPacket
from studio.manifest import Block, CreativeManifest, MediaAsset, Provenance


class StudioStep(BaseModel):
    agent: str
    model: str
    output: dict = Field(default_factory=dict)


class StudioTrace(BaseModel):
    run_id: str
    project: str
    inputs_hash: str
    steps: list[StudioStep] = Field(default_factory=list)


class StudioResult(BaseModel):
    manifest: CreativeManifest
    trace: StudioTrace
    verdict: dict


def _hash_packet(packet: HarvestPacket) -> str:
    payload = json.dumps(packet.model_dump(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run(packet: HarvestPacket, siblings: list | None = None) -> StudioResult:
    run_id = str(uuid.uuid4())
    inputs_hash = _hash_packet(packet)
    steps: list[StudioStep] = []

    brief = agents.art_director(packet)
    steps.append(StudioStep(agent="art_director", model="claude-opus-4-8", output=brief.model_dump()))

    copy_blocks = agents.copywriter(packet, brief)
    steps.append(StudioStep(agent="copywriter", model="claude-sonnet-5", output={"blocks": copy_blocks}))

    media_assets = agents.media(packet, brief)
    steps.append(StudioStep(agent="media", model="claude-sonnet-5", output={"media": media_assets}))

    arranged = agents.assembler(packet, brief, copy_blocks, media_assets)
    steps.append(StudioStep(agent="assembler", model="claude-sonnet-5", output={"blocks": arranged}))

    manifest = CreativeManifest(
        project=packet.project,
        brief=brief,
        blocks=[Block(**b) for b in arranged],
        media=[MediaAsset(**m) for m in media_assets],
        provenance=Provenance(
            run_id=run_id,
            generated_by="claude-opus-4-8",
            prompt_template="art_director@v1",
            inputs_hash=inputs_hash,
        ),
    )

    failures = guardrails.check(manifest, siblings=siblings)
    verdict = {"pass": not failures, "failures": failures}
    steps.append(StudioStep(agent="qa", model="deterministic", output=verdict))

    trace = StudioTrace(run_id=run_id, project=packet.project, inputs_hash=inputs_hash, steps=steps)
    return StudioResult(manifest=manifest, trace=trace, verdict=verdict)


def save_run(result: StudioResult, base_dir: Path) -> Path:
    """Persiste le run (manifest + trace + verdict) de façon IMMUABLE (par run_id)."""
    path = base_dir / "runs" / f"{result.trace.run_id}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(result.model_dump(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path
