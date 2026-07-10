"""Schémas Pydantic du module onboarding (Chap 5)."""

from pydantic import BaseModel, ConfigDict


class OnboardingAnswer(BaseModel):
    flow_id: str
    answers: dict[str, str]


class OnboardingResult(BaseModel):
    # extra="ignore" : les écrans de résultat peuvent porter des clés en plus.
    model_config = ConfigDict(extra="ignore")

    profile: str
    score: int
    title: str = ""
    description: str = ""
    label: str = ""


class FlowQuestions(BaseModel):
    questions: list[dict]
