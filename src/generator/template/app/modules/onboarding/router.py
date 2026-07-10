"""Routeur du module onboarding (Chap 12).

- GET  /flows/{id} : questions du flow (public).
- POST /evaluate   : score les réponses -> profil + écran (public, sans persistance).
- POST /profile    : idem + persiste le UserProfile de l'utilisateur connecté.
Monté sous /api/onboarding par le core.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_current_user
from app.core.database import get_db
from app.core.models import User
from app.modules.onboarding.engine import (
    FlowNotFound,
    evaluate_scoring,
    load_flow,
    load_result_screen,
)
from app.modules.onboarding.models import UserProfile
from app.modules.onboarding.schemas import (
    FlowQuestions,
    OnboardingAnswer,
    OnboardingResult,
)

router = APIRouter()


def _evaluate(answer: OnboardingAnswer) -> OnboardingResult:
    try:
        flow = load_flow(answer.flow_id)
    except FlowNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Flow introuvable"
        )
    result = evaluate_scoring(flow, answer.answers)
    screen = load_result_screen(flow, result["profile"])
    return OnboardingResult(profile=result["profile"], score=result["score"], **screen)


@router.get("/flows/{flow_id}", response_model=FlowQuestions)
async def get_flow(flow_id: str) -> FlowQuestions:
    try:
        flow = load_flow(flow_id)
    except FlowNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Flow introuvable"
        )
    return FlowQuestions(questions=flow["questions"])


@router.post("/evaluate", response_model=OnboardingResult)
async def evaluate(answer: OnboardingAnswer) -> OnboardingResult:
    return _evaluate(answer)


@router.post("/profile", response_model=OnboardingResult)
async def save_profile(
    answer: OnboardingAnswer,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OnboardingResult:
    result = _evaluate(answer)
    existing = (
        await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            UserProfile(
                user_id=user.id,
                flow_id=answer.flow_id,
                answers=answer.answers,
                profile=result.profile,
                score=result.score,
            )
        )
    else:
        existing.flow_id = answer.flow_id
        existing.answers = answer.answers
        existing.profile = result.profile
        existing.score = result.score
    await db.commit()
    return result
