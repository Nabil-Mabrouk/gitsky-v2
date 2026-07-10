"""Schémas Pydantic du module tutorials (Chap 5)."""

from pydantic import BaseModel, ConfigDict

from app.core.models import UserRole


class LessonSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    order: int


class LessonRead(LessonSummary):
    content: str


class TutorialSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    slug: str
    lang: str
    access_role: UserRole


class TutorialDetail(TutorialSummary):
    lessons: list[LessonSummary]
