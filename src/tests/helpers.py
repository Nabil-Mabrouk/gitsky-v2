"""Utilitaires partagés des tests de génération.

Le nettoyage temp sous Windows est piégeux dès qu'un projet généré est en jeu :
les `_tasks` de Copier lancent `git init`/`git add`, et un .git contient des
objets en LECTURE SEULE — `shutil.rmtree` échoue alors en PermissionError.
S'y ajoutent des handles brièvement retenus (processus git qui vient de sortir,
antivirus), d'où le backoff.

Historique : cette logique était dupliquée dans 5 fichiers de tests. Les
nouveaux tests passent par ici ; les anciens pourront migrer au fil de l'eau.
"""

import os
import shutil
import stat
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from copier import run_copy

GENERATOR = Path(__file__).resolve().parents[1] / "generator"


def rmtree_robuste(path: Path) -> None:
    """Supprime une arborescence contenant potentiellement un .git Windows."""

    def _onexc(func, p, exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    for essai in range(5):
        try:
            shutil.rmtree(path, onexc=_onexc)
            return
        except (PermissionError, OSError):
            if essai == 4:
                raise
            time.sleep(0.2 * (essai + 1))


@contextmanager
def projet_temporaire() -> Iterator[Path]:
    """Cède un chemin de destination pour un projet généré, nettoyé à la sortie.

    À utiliser partout où `tempfile.TemporaryDirectory()` recevrait un projet
    généré : son nettoyage à lui ne survit pas au .git laissé par les _tasks.
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        yield tmp / "proj"
    finally:
        rmtree_robuste(tmp)


@contextmanager
def projet_genere(name: str, **data) -> Iterator[Path]:
    """Génère un projet SANS les _tasks (git init/add/commit) et cède son chemin.

    Les tests qui ne font que LIRE des fichiers générés n'ont aucun besoin du
    commit initial — et ce `git add -A` est la source d'une flakiness Windows
    tenace (antivirus verrouillant les objets .git fraîchement créés pendant
    l'exécution de la tâche). `skip_tasks=True` supprime la cause à la racine
    et accélère nettement ces tests. Les tests qui vérifient les _tasks
    eux-mêmes (commit initial, provision) génèrent avec les tâches, à part.
    """
    with projet_temporaire() as dst:
        run_copy(
            str(GENERATOR),
            str(dst),
            data={"project": {"name": name}, **data},
            defaults=True,
            quiet=True,
            unsafe=True,
            skip_tasks=True,
        )
        yield dst
