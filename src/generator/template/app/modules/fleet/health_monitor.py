"""Monitoring de disponibilité de flotte (Chap 23 §« Monitoring de Disponibilité »).

Un cron interroge `/health` sur tous les projets toutes les 60 s et tient à jour,
par projet, l'horodatage du dernier succès. Ce module décide — à partir de ces
horodatages — quels projets sont MUETS (> 5 min) et journalise l'alerte
`deployment_failed` du fleet dashboard (Chap 19), ainsi que la reprise.

Séparation nette (comme `kill_check`) : la décision est PURE et testable ; l'I/O
réseau (le poll HTTP) est faite par le poller, qui alimente `record_health_sweep`.
Un seul événement par transition — pas un `deployment_failed` toutes les 60 s.
"""

from collections.abc import Mapping
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fleet.models import FleetLifecycleEvent, Project

# Le livre : « muet depuis plus de 5 minutes déclenche deployment_failed ».
SILENCE_THRESHOLD = timedelta(minutes=5)

DEPLOYMENT_FAILED = "deployment_failed"
DEPLOYMENT_RECOVERED = "deployment_recovered"
_AVAILABILITY_EVENTS = (DEPLOYMENT_FAILED, DEPLOYMENT_RECOVERED)


def is_silent(
    now: datetime,
    last_success: datetime | None,
    threshold: timedelta = SILENCE_THRESHOLD,
) -> bool:
    """Un projet est muet s'il n'a jamais répondu ou pas depuis `threshold`.

    Pur : aucune I/O. `last_success` None = aucun succès connu -> muet.
    """
    if last_success is None:
        return True
    return (now - last_success) > threshold


async def _last_availability_event(db: AsyncSession, project_name: str) -> str | None:
    """Dernier événement de disponibilité journalisé pour ce projet (ou None)."""
    row = (
        await db.execute(
            select(FleetLifecycleEvent.event_type)
            .where(
                FleetLifecycleEvent.project_name == project_name,
                FleetLifecycleEvent.event_type.in_(_AVAILABILITY_EVENTS),
            )
            .order_by(FleetLifecycleEvent.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return row


async def record_health_sweep(
    db: AsyncSession,
    last_success: Mapping[str, datetime | None],
    now: datetime,
) -> dict[str, list[str]]:
    """Journalise les transitions de disponibilité et retourne ce qui a changé.

    - Un projet muet dont le dernier événement n'est pas déjà `deployment_failed`
      -> on émet `deployment_failed` (dédup : une seule alerte par panne).
    - Un projet redevenu joignable après une panne -> `deployment_recovered`.
    - Les projets `killed` sont ignorés (un kill n'est pas une panne).
    """
    projects = (
        await db.execute(select(Project).where(Project.status != "killed"))
    ).scalars().all()

    changed: dict[str, list[str]] = {"failed": [], "recovered": []}

    for project in projects:
        silent = is_silent(now, last_success.get(project.name))
        previous = await _last_availability_event(db, project.name)

        if silent and previous != DEPLOYMENT_FAILED:
            db.add(
                FleetLifecycleEvent(
                    project_name=project.name,
                    event_type=DEPLOYMENT_FAILED,
                    tier=project.tier,
                    reason="muet > 5 min sur /health",
                )
            )
            changed["failed"].append(project.name)
        elif not silent and previous == DEPLOYMENT_FAILED:
            db.add(
                FleetLifecycleEvent(
                    project_name=project.name,
                    event_type=DEPLOYMENT_RECOVERED,
                    tier=project.tier,
                    reason="/health de nouveau joignable",
                )
            )
            changed["recovered"].append(project.name)

    await db.commit()
    return changed
