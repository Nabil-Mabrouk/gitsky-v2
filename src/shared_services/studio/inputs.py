"""Entrée du pipeline Studio — le Harvest Packet (Chap 24)."""

from pydantic import BaseModel, Field


class HarvestPacket(BaseModel):
    project: str
    idea_oneliner: str
    audience: str = ""
    vertical: str = ""
    target_lang: str = "fr"
    source_excerpts: list[str] = Field(default_factory=list)
    tier: str = "t0"
    operator_seeds: dict = Field(default_factory=dict)
