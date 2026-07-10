"""Schémas Pydantic du module fleet (Chap 5)."""

from pydantic import BaseModel, ConfigDict


class ProjectRegister(BaseModel):
    name: str
    tier: str
    domain: str = ""
    template_version: str = ""


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    tier: str
    domain: str | None
    status: str
    template_version: str | None
