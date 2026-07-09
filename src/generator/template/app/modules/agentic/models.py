"""Modèle du module `agentic` (Chap 15).

Table cœur de traçabilité `service_executions`. Le livre prévoit trois tables
supplémentaires (steps, results, preferences) — raffinements ultérieurs.
"""

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, func

from app.core.database import Base


class ServiceExecution(Base):
    __tablename__ = "service_executions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    service_slug = Column(String, index=True, nullable=False)
    workflow_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending/running/completed/failed
    input_params = Column(JSON)
    result = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
