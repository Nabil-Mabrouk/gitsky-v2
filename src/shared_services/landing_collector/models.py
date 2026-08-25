"""Modèle du landing collector (Chap 18)."""

from sqlalchemy import Boolean, Column, DateTime, Integer, String, func

from landing_collector.database import Base


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    project = Column(String, index=True, nullable=False)
    email = Column(String, nullable=False)
    source = Column(String)
    utm_campaign = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # Double opt-in (Chap 18) : verify_token est vidé après confirmation
    # (usage unique), même stratégie que User.invite_token côté fleet-dashboard.
    verified = Column(Boolean, nullable=False, default=False, server_default="false")
    verify_token = Column(String, nullable=True)
