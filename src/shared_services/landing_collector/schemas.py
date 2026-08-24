"""Schémas Pydantic du landing collector."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class LeadIn(BaseModel):
    project: str
    email: EmailStr
    source: str = ""
    utm_campaign: str = ""


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
