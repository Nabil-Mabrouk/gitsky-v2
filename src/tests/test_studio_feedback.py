"""Boucle de feedback conversion -> direction artistique (Phase 5, incrément 8)."""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC / "shared_services"))

from studio.feedback import aggregate_conversion, best_skin  # noqa: E402


def test_aggregate_conversion_by_skin():
    samples = [
        {"skin": "clean", "converted": True},
        {"skin": "clean", "converted": False},
        {"skin": "editorial", "converted": True},
        {"skin": "editorial", "converted": True},
    ]
    rates = aggregate_conversion(samples)
    assert rates["clean"] == 0.5
    assert rates["editorial"] == 1.0


def test_best_skin_picks_top_converter():
    assert best_skin({"clean": 0.3, "editorial": 0.7, "bold": 0.5}) == "editorial"


def test_best_skin_default_when_empty():
    assert best_skin({}) == "clean"
