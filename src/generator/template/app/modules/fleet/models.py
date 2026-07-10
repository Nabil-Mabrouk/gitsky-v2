"""Modèles du module `fleet` (Chap 19 / Chap 20).

Le fleet dashboard ne duplique PAS les métriques (agrégées en direct), mais il
possède deux tables : le registre des projets et le journal de cycle de vie
(`fleet_lifecycle_events`, seul journal transversal persistant).
"""

from sqlalchemy import Column, DateTime, Integer, String, func

from app.core.database import Base


class Project(Base):
    __tablename__ = "fleet_projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    tier = Column(String, nullable=False)
    domain = Column(String)
    status = Column(String, nullable=False, default="active")  # active/pending_kill/killed
    publish_status = Column(String, nullable=False, default="draft")  # draft/preview/live
    template_version = Column(String)
    first_deployed_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class FleetLifecycleEvent(Base):
    __tablename__ = "fleet_lifecycle_events"

    id = Column(Integer, primary_key=True, index=True)
    project_name = Column(String, index=True, nullable=False)
    event_type = Column(String, nullable=False)  # born/promoted/pending_kill/killed
    tier = Column(String)
    reason = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
