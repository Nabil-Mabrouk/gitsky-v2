"""Schémas Pydantic du module agentic (Chap 5)."""

from typing import Any

from pydantic import BaseModel, ConfigDict


class ServiceSummary(BaseModel):
    slug: str
    name: str
    description: str
    category: str


class ExecuteRequest(BaseModel):
    workflow_name: str
    parameters: dict[str, Any] = {}


class ExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    service_slug: str
    workflow_name: str
    status: str
    result: dict[str, Any] | None
