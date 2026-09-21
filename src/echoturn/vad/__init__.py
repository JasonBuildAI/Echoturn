"""Deciding whether somebody spoke, and for how long.

Two engines, one shape of answer. The model is the default because it answers the
question that matters - how much real speech was there - while the level-based
detector only answers how loud it was.

:func:`build_vad` decides which one actually runs and always says so. A host that
configured the model and did not get it needs to find that out from the answer,
not from a log line it does not read: "I chose the model" turning silently into
"a level threshold" is the kind of degradation that gets discovered weeks later,
by a user complaining that it interrupts them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import dials
from .energy import DEFAULT_FLOOR, EnergyVad
from .segments import speech_ms
from .silero import MODEL_FILE, SileroVad

__all__ = [
    "MODEL_FILE",
    "EnergyVad",
    "SileroVad",
    "Vad",
    "build_vad",
    "speech_ms",
]

ENGINES = ("silero", "energy")


@dataclass(frozen=True)
class Vad:
    """What will actually measure speech, and whether it is what was asked for."""

    engine: str
    fallback: bool
    reason: str
    detector: Any

    def report(self, samples) -> dict:
        """Speech length for one recording, or an empty report if unmeasurable."""
        try:
            return self.detector.report(samples) or {}
        except Exception as exc:  # noqa: BLE001 - a detector must not fail a turn
            return {"engine": self.engine, "error": f"{type(exc).__name__}: {exc}"}


def build_vad(
    engine: str | None = None,
    *,
    model_path: str | None = None,
    floor: float | None = None,
) -> Vad:
    """Choose a detector, falling back visibly when the model is not there.

    The engine is read from the dial table when the caller does not name one, so
    that a host can change it at runtime. An engine name that is not one of ours
    is treated as the model engine rather than refused: this runs on the path of
    a live conversation, and a typo in a config file should not stop the audio.
    """
    wanted = str(engine or dials()["vad_engine"] or "energy").strip().lower()
    if wanted not in ENGINES:
        wanted = "silero"
    if wanted == "energy":
        return Vad("energy", False, "", _energy(floor))
    detector = SileroVad(model_path)
    if detector.ready():
        return Vad("silero", False, "", detector)
    return Vad(
        "energy",
        True,
        f"the speech model is not at {detector.path}; using the level detector",
        _energy(floor),
    )


def _energy(floor: float | None) -> EnergyVad:
    """The level detector, with the shipped floor unless one was given."""
    return EnergyVad(DEFAULT_FLOOR if floor is None else floor)
