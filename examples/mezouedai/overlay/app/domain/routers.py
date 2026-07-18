"""Routeurs métier de MezouedAI (overlay projet — remplace le stub scaffoldé).

- GET  /api/songs/catalog : catalogue de référence (chanteurs, thèmes, rythmes,
  instruments). Statique en T1 ; en prod ces tables scaffoldées (Singer/Theme/
  Rhythm/Instrument, cf. data_models) seraient seedées et lues ici.
- POST /api/songs         : sauvegarde la spec composée par l'utilisateur connecté.
- GET  /api/songs         : liste les chansons de l'utilisateur.

Le core inclut automatiquement tout `*_router` de ce module (voir main.py).
"""

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_current_user
from app.core.database import get_db
from app.core.models import User
from app.domain.models import Song

songs_router = APIRouter(prefix="/api/songs", tags=["songs"])

# Catalogue de référence (statique en T1). Voix = identifiant de timbre passé
# plus tard au tool Suno (T2).
CATALOG = {
    "singers": [
        {"name": "Slah", "voice": "warm-baritone", "avatar": "🎤", "tagline": "Voix chaude et ronde"},
        {"name": "Naïma", "voice": "bright-alto", "avatar": "🎶", "tagline": "Timbre clair et vif"},
        {"name": "Hédi", "voice": "raspy-tenor", "avatar": "🕌", "tagline": "Grain rocailleux traditionnel"},
    ],
    "themes": [
        {"name": "Amour", "description": "Chansons de cœur"},
        {"name": "Fête", "description": "Ambiance de mariage et de joie"},
        {"name": "Exil", "description": "Nostalgie et pays"},
    ],
    "rhythms": [
        {"name": "Fezzani", "bpm": 120, "description": "Rythme de mezoued classique"},
        {"name": "Saltana", "bpm": 100, "description": "Balancé, méditatif"},
        {"name": "Allala", "bpm": 140, "description": "Rapide et festif"},
    ],
    "instruments": [
        {"name": "Mezoued", "family": "vent"},
        {"name": "Darbouka", "family": "percussion"},
        {"name": "Bendir", "family": "percussion"},
        {"name": "Zokra", "family": "vent"},
    ],
}


class SongSpec(BaseModel):
    title: str = "Sans titre"
    singer: str = ""
    theme: str = ""
    rhythm: str = ""
    instruments: list[str] = Field(default_factory=list)
    structure: list[str] = Field(default_factory=list)


class SongRead(BaseModel):
    id: int
    title: str
    status: str
    structure: list[str]


@songs_router.get("/catalog")
async def catalog() -> dict:
    return CATALOG


@songs_router.post("", response_model=SongRead)
async def create_song(
    spec: SongSpec,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SongRead:
    song = Song(
        user_id=user.id,
        title=spec.title,
        singer=spec.singer,
        theme=spec.theme,
        rhythm=spec.rhythm,
        instruments=json.dumps(spec.instruments, ensure_ascii=False),
        structure=json.dumps(spec.structure, ensure_ascii=False),
        lyrics="",
        status="draft",
        audio_url="",
    )
    db.add(song)
    await db.commit()
    await db.refresh(song)
    return SongRead(id=song.id, title=song.title, status=song.status, structure=spec.structure)


@songs_router.get("", response_model=list[SongRead])
async def list_songs(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SongRead]:
    rows = (
        await db.execute(select(Song).where(Song.user_id == user.id))
    ).scalars().all()
    return [
        SongRead(
            id=s.id,
            title=s.title,
            status=s.status,
            structure=json.loads(s.structure or "[]"),
        )
        for s in rows
    ]
