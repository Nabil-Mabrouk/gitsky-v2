"""Modèle du module `onboarding` (Chap 4 / Chap 12).

Relation 1:1 avec User. `answers` en JSON (les réponses brutes du questionnaire).
"""

from sqlalchemy import JSON, Column, ForeignKey, Integer, String

from app.core.database import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    flow_id = Column(String, nullable=False)
    answers = Column(JSON)
    profile = Column(String)
    score = Column(Integer)
