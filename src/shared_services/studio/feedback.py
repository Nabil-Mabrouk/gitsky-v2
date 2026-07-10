"""Boucle de feedback du Studio (Chap 24) — la vraie douve.

Le fleet dashboard mesure la conversion par landing (Chap 19). On agrège la
conversion PAR DIRECTION ARTISTIQUE (skin) pour biaiser les choix futurs du
directeur artistique : le Studio s'améliore parce qu'il est câblé à un
portefeuille de données de conversion réelles. Logique pure et testable.
"""

from collections import defaultdict


def aggregate_conversion(samples: list[dict]) -> dict[str, float]:
    """samples: [{"skin": str, "converted": bool}] -> taux de conversion par skin."""
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [converted, total]
    for sample in samples:
        counts[sample["skin"]][1] += 1
        if sample.get("converted"):
            counts[sample["skin"]][0] += 1
    return {
        skin: (converted / total if total else 0.0)
        for skin, (converted, total) in counts.items()
    }


def best_skin(rates: dict[str, float], default: str = "clean") -> str:
    """Le skin qui convertit le mieux (biais réinjecté au directeur artistique)."""
    if not rates:
        return default
    return max(rates, key=lambda skin: rates[skin])
