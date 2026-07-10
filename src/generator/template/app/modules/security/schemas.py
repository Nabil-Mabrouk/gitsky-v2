"""Schémas Pydantic du module security (Chap 5)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SecurityEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    severity: str
    ip_address: str | None
    path: str | None
    created_at: datetime | None


class SecuritySummary(BaseModel):
    total: int
    by_severity: dict[str, int]
