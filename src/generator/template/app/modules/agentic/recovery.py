"""Récupération des exécutions agentic orphelines (durcissement Chap 15).

Les workflows longs tournent dans des `asyncio.Task` en mémoire : un
redémarrage (deploy, crash, OOM) les emporte sans trace. Sans rattrapage, les
exécutions restaient `pending`/`running` pour toujours et les crédits débités
n'étaient jamais remboursés.

Appelé au démarrage (lifespan) : à cet instant aucune tâche ne tourne encore,
donc toute exécution non terminale est par définition orpheline.
"""

from sqlalchemy import select

from app.modules.agentic import credits
from app.modules.agentic.models import ServiceExecution

_ORPHAN_STATUSES = ("pending", "running")


async def recover_orphan_executions(session_factory) -> int:
    """Clôt en `failed` les exécutions orphelines et rembourse leur coût.

    Renvoie le nombre d'exécutions rattrapées.
    """
    async with session_factory() as db:
        orphans = (
            (
                await db.execute(
                    select(ServiceExecution).where(
                        ServiceExecution.status.in_(_ORPHAN_STATUSES)
                    )
                )
            )
            .scalars()
            .all()
        )
        for execution in orphans:
            execution.status = "failed"
            execution.result = {
                "error": "exécution interrompue par un redémarrage du serveur"
            }
            if execution.cost_credits:
                await credits.refund(db, execution.user_id, execution.cost_credits)
        await db.commit()
        return len(orphans)
