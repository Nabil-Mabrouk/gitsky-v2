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
