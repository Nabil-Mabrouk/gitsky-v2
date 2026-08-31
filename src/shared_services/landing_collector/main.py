"""API du landing collector (Chap 18).

- POST /leads                : une landing T0 poste une capture d'email.
- GET  /leads/verify/{token} : confirme l'email (double opt-in).
- GET  /leads/{project}/stats : le fleet dashboard lit le funnel du projet.
- GET  /leads/{project}      : le fleet dashboard lit la liste des leads.

Les tables sont créées au démarrage (service minimal, pas d'Alembic).
"""

import hashlib
import hmac
import logging
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from landing_collector import mailer
from landing_collector.database import create_tables, get_session
from landing_collector.models import Lead
from landing_collector.schemas import LeadIn, LeadOut, LeadStats

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(title="Landing Collector", lifespan=lifespan)

_INVALID_TOKEN_HTML = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Lien invalide</title></head><body style="font-family: sans-serif; text-align: center; padding: 4rem;">
<h1>Ce lien de confirmation est invalide ou a déjà été utilisé.</h1></body></html>"""

_CONFIRMED_HTML = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Email confirmé</title></head><body style="font-family: sans-serif; text-align: center; padding: 4rem;">
<h1>Merci, votre email est confirmé !</h1></body></html>"""


@app.post("/leads")
async def collect_lead(lead: LeadIn, db: AsyncSession = Depends(get_session)) -> dict:
    # Anti-abus : une soumission répétée du même (project, email) ne doit ni
    # dupliquer la ligne ni renvoyer un email — sinon le formulaire public
    # devient un vecteur de spam vers n'importe quelle adresse tierce. Check
    # applicatif (pas de contrainte UNIQUE : pas d'Alembic pour l'ajouter
    # proprement sur une table déjà en production), tolérable vu le volume.
    existing = (
        await db.execute(
            select(Lead).where(Lead.project == lead.project, Lead.email == lead.email)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {"ok": True}

    token = secrets.token_urlsafe(32)
    db.add(
        Lead(
            project=lead.project,
            email=lead.email,
            source=lead.source,
            utm_campaign=lead.utm_campaign,
            verified=False,
            verify_token=token,
        )
    )
    await db.commit()

    # L'envoi d'email ne doit jamais faire échouer la capture — même
    # raisonnement que la génération d'image du Studio (Round B) : la donnée
    # est la source de vérité, l'email est un enrichissement.
    if lead.domain:
        link = f"https://{lead.domain}/leads/verify/{token}"
        try:
            mailer.send_email(
                to=lead.email,
                subject="Confirmez votre inscription",
                body=(
                    f"Cliquez sur ce lien pour confirmer votre inscription : {link}\n\n"
                    "Si vous n'êtes pas à l'origine de cette demande, ignorez cet email."
                ),
            )
        except Exception:
            logger.exception("Échec d'envoi de l'email de confirmation à %s", lead.email)
    else:
        logger.warning("Pas de domaine fourni pour %s, email de confirmation ignoré", lead.project)

    return {"ok": True}


@app.get("/leads/verify/{token}", response_class=HTMLResponse)
async def verify_lead(token: str, db: AsyncSession = Depends(get_session)) -> HTMLResponse:
    lead = (
        await db.execute(select(Lead).where(Lead.verify_token == token))
    ).scalar_one_or_none()
    if lead is None:
        return HTMLResponse(_INVALID_TOKEN_HTML, status_code=status.HTTP_404_NOT_FOUND)

    lead.verified = True
    lead.verify_token = None
    await db.commit()
    return HTMLResponse(_CONFIRMED_HTML)


def _derived_token(master: str, project: str) -> str:
    """Jeton par-projet dérivé du jeton maître (module_leads, round leads).

    HMAC-SHA256(COLLECTOR_STATS_TOKEN, project) — dupliqué à l'identique dans
    app/modules/fleet/generator_client.py (calcul automatique à la création
    d'un projet) et scripts/provision_leads_token.sh (provisioning manuel/
    retrofit) du générateur. Aucun paquet partagé entre shared_services/ et
    src/generator/template/ (unités déployées séparément, même doctrine que
    LeadRead/LeadOut : miroir local plutôt qu'import cross-service) — toute
    dérive entre les trois casserait silencieusement l'accès d'un projet à
    ses propres leads ; test_collector_stats_token.py verrouille la formule.
    """
    return hmac.new(master.encode(), project.encode(), hashlib.sha256).hexdigest()


async def verify_stats_token(
    project: str,
    x_collector_token: str | None = Header(default=None),
) -> None:
    """Garde de lecture des stats/leads (durcissement, même sémantique que fleet).

    La CAPTURE (/leads) reste publique — les landings T0 postent sans secret.
    La LECTURE, elle, accepte SOIT le jeton maître (fleet dashboard, accès
    fleet-wide inchangé) SOIT le jeton DÉRIVÉ du projet demandé (module_leads
    d'un projet ordinaire, round leads) : HMAC-SHA256(COLLECTOR_STATS_TOKEN,
    project). `project` est injecté par FastAPI depuis le paramètre de
    chemin {project} de la route appelante, comme pour le handler lui-même.

    Sans cette distinction par projet, donner à chaque projet le même jeton
    que fleet-dashboard lui ouvrirait la lecture des leads de TOUTE la
    flotte — `project` est un paramètre de chemin libre, sans registre ni
    scoping par appelant.

    Token absent -> ouvert en dev, refus en production (fail-closed),
    inchangé.
    """
    expected = os.environ.get("COLLECTOR_STATS_TOKEN", "")
    if not expected:
        if os.environ.get("ENVIRONMENT", "").lower() == "production":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="COLLECTOR_STATS_TOKEN non configuré",
            )
        return
    if x_collector_token is not None and (
        secrets.compare_digest(x_collector_token, expected)
        or secrets.compare_digest(x_collector_token, _derived_token(expected, project))
    ):
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide")


@app.get(
    "/leads/{project}/stats",
    response_model=LeadStats,
    dependencies=[Depends(verify_stats_token)],
)
async def project_stats(
    project: str, db: AsyncSession = Depends(get_session)
) -> LeadStats:
    signups = (
        await db.execute(
            select(func.count()).select_from(Lead).where(Lead.project == project)
        )
    ).scalar_one()
    return LeadStats(project=project, signups=signups)


@app.get(
    "/leads/{project}",
    response_model=list[LeadOut],
    dependencies=[Depends(verify_stats_token)],
)
async def list_leads(
    project: str, limit: int = 200, db: AsyncSession = Depends(get_session)
) -> list[Lead]:
    # Pas d'offset/curseur : volume attendu faible (produits en phase T0), un
    # `limit` fixe suffit comme garde-fou sans complexité de pagination.
    # Tri secondaire sur id : deux leads captés dans la même seconde (rafale
    # de trafic) auraient sinon un ordre indéfini malgré le tri sur created_at.
    result = await db.execute(
        select(Lead)
        .where(Lead.project == project)
        .order_by(Lead.created_at.desc(), Lead.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
