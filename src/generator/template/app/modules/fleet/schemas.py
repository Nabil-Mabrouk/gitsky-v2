"""Schémas Pydantic du module fleet (Chap 5)."""

from datetime import datetime

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
    publish_status: str
    template_version: str | None


class PromoteRequest(BaseModel):
    guardrails_pass: bool = True
    human_approved: bool = False


class PromoteResult(BaseModel):
    project: str
    publish_status: str
    allowed: bool
    reason: str


class KillCheckMetrics(BaseModel):
    days_since_deploy: int = 0
    signup_count: int = 0
    visit_count: int = 0
    conversion_rate: float = 0.0
    qualitative_feedback_count: int = 0
    total_cost: float = 0.0
    active_users_last_7d: int = 0
    retention_d7: float = 0.0
    paid_users_count: int = 0
    wtp_declarations: int = 0
    mrr: float = 0.0
    churn_rate_3m: float = 0.0
    days_below_mrr_threshold: int = 0


class KillCheckResult(BaseModel):
    project: str
    tier: str
    verdict: str
    status: str


class HealthSweepRequest(BaseModel):
    # Dernier succès /health par projet (le poller le tient à jour). null =
    # aucun succès connu. `now` optionnel : sinon l'heure serveur fait foi.
    last_success: dict[str, datetime | None]
    now: datetime | None = None


class HealthSweepResult(BaseModel):
    failed: list[str]
    recovered: list[str]
