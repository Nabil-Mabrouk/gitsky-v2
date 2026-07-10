"""Schémas Pydantic du landing collector."""

from pydantic import BaseModel, EmailStr


class LeadIn(BaseModel):
    project: str
    email: EmailStr
    source: str = ""
    utm_campaign: str = ""


class LeadStats(BaseModel):
    project: str
    signups: int
