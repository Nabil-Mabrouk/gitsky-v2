"""Modèle du module `analytics` (Chap 4 / Chap 13).

Tracking anonymisé RGPD : l'IP n'est JAMAIS stockée en clair, seulement un hash
salé (`ip_hash`). Correspond à la chaîne Alembic `visits`.
"""

from sqlalchemy import Column, DateTime, Integer, String, func

from app.core.database import Base


class Visit(Base):
    __tablename__ = "visits"

    id = Column(Integer, primary_key=True, index=True)
    ip_hash = Column(String, index=True)
    country_code = Column(String(2), index=True)
    city = Column(String)
    path = Column(String)
    user_role = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
