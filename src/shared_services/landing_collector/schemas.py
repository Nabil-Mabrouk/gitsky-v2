"""Schémas Pydantic du landing collector."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class LeadIn(BaseModel):
    project: str
    email: EmailStr
    source: str = ""
    utm_campaign: str = ""
    # Transitoire : sert uniquement à construire le lien de vérification
    # (landing-collector ne connaît pas le domaine des projets, contrairement
    # à fleet-dashboard) — jamais persisté, pas de colonne dédiée sur Lead.
    domain: str = ""


class LeadStats(BaseModel):
    project: str
    signups: int


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project: str
    email: str
    source: str | None
    utm_campaign: str | None
    created_at: datetime | None
    verified: bool
