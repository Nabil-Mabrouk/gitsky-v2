"""Modèles du module `agentic` (Chap 15).

- `ServiceExecution` : cœur de traçabilité d'une exécution de workflow.
- `ExecutionStep` : une étape du workflow (la table `steps` annoncée dès l'origine)
  — checkpoint pour l'audit et la reprise d'un job interrompu.
- `CreditAccount` : portefeuille de crédits (une génération payante débite ici).
"""

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, func

from app.core.database import Base


class ServiceExecution(Base):
    __tablename__ = "service_executions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    service_slug = Column(String, index=True, nullable=False)
    workflow_name = Column(String, nullable=False)
    # pending -> running -> completed | failed. (awaiting_callback : réservé au
    # cas d'un tool réellement asynchrone repris par webhook — non exercé par le
    # stub, voir tools/suno.py.)
    status = Column(String, nullable=False, default="pending")
    input_params = Column(JSON)
    result = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ExecutionStep(Base):
    __tablename__ = "execution_steps"

    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(
        Integer, ForeignKey("service_executions.id"), index=True, nullable=False
    )
    idx = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    kind = Column(String, nullable=False)  # agent | tool
    status = Column(String, nullable=False, default="pending")
    output = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CreditAccount(Base):
    __tablename__ = "credit_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id"), unique=True, index=True, nullable=False
    )
    balance = Column(Integer, nullable=False, default=0)
