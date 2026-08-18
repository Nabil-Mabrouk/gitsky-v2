"""Seed de contenu tutoriels depuis un dossier de fichiers Markdown (Chap 11).

Générique : ne connaît rien du contenu réel qu'on lui donne (livre GitSky ou
autre) — lit chaque `.md` d'un dossier, triés par nom de fichier, la 1re
ligne `# Titre` devient le titre de la leçon, le reste le contenu. Upsert par
(slug du tutoriel, ordre de la leçon) : rejouable après une édition du
contenu source sans dupliquer de lignes.

Usage (dans le conteneur backend, même pattern que scripts/migrate.py) :
    python -m scripts.seed_tutorials --slug operer-gitsky \
        --title "Opérer GitSky" --lang fr --access-role admin \
        /path/to/markdown-dir
"""

import argparse
import asyncio
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import SessionLocal
from app.core.models import UserRole
from app.modules.tutorials.models import Lesson, Tutorial


def _parse_lesson(path: Path) -> tuple[str, str]:
    """Première ligne `# Titre` -> titre de la leçon ; le reste -> contenu."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()
        content = "\n".join(lines[1:]).strip()
    else:
        title = path.stem
        content = text.strip()
    return title, content


async def seed(
    markdown_dir: Path,
    slug: str,
    title: str,
    lang: str,
    access_role: UserRole,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> int:
    factory = session_factory or SessionLocal
    files = sorted(markdown_dir.glob("*.md"))
    if not files:
        raise SystemExit(f"Aucun fichier .md dans {markdown_dir}")

    async with factory() as db:
        tutorial = (
            await db.execute(select(Tutorial).where(Tutorial.slug == slug))
        ).scalar_one_or_none()
        if tutorial is None:
            tutorial = Tutorial(slug=slug, title=title, lang=lang, access_role=access_role)
            db.add(tutorial)
            await db.flush()  # assigne tutorial.id avant les requêtes Lesson ci-dessous
        else:
            tutorial.title = title
            tutorial.lang = lang
            tutorial.access_role = access_role

        for order, path in enumerate(files, start=1):
            lesson_title, content = _parse_lesson(path)
            lesson = (
                await db.execute(
                    select(Lesson).where(
                        Lesson.tutorial_id == tutorial.id, Lesson.order == order
                    )
                )
            ).scalar_one_or_none()
            if lesson is None:
                db.add(
                    Lesson(
                        tutorial_id=tutorial.id,
                        title=lesson_title,
                        content=content,
                        order=order,
                    )
                )
            else:
                lesson.title = lesson_title
                lesson.content = content

        await db.commit()
        return len(files)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown_dir", type=Path)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--lang", default="fr")
    parser.add_argument(
        "--access-role",
        choices=[r.value for r in UserRole],
        default=UserRole.user.value,
    )
    args = parser.parse_args()

    count = asyncio.run(
        seed(
            args.markdown_dir,
            args.slug,
            args.title,
            args.lang,
            UserRole(args.access_role),
        )
    )
    print(f"{count} leçon(s) upsertée(s) pour le tutoriel « {args.slug} ».")


if __name__ == "__main__":
    main()
