"""Modèles du module `tutorials` (Chap 4 / Chap 11).

Relation One-to-Many Tutorial -> Lesson. Dépend uniquement du core
(`app.core`), jamais d'un autre module (contrat d'isolation Chap 11).
"""

from sqlalchemy import Column, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.models import UserRole


class Tutorial(Base):
    __tablename__ = "tutorials"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    lang = Column(String(5), default="fr", index=True, nullable=False)
    access_role = Column(Enum(UserRole), default=UserRole.user, nullable=False)

    lessons = relationship(
        "Lesson",
        back_populates="tutorial",
        order_by="Lesson.order",
        cascade="all, delete-orphan",
    )


class Lesson(Base):
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True, index=True)
    tutorial_id = Column(
        Integer,
        ForeignKey("tutorials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False, default="")
    order = Column(Integer, default=0, nullable=False)

    tutorial = relationship("Tutorial", back_populates="lessons")
