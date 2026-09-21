"""Deciding whether a turn has ended, and saying when nothing can decide.

:func:`build_turn` is the counterpart of :func:`echoturn.vad.build_vad`: it picks
the judge that will actually run and reports which one that is. These are two
different situations and must not read the same from the outside - a host that
turned the model off, and a host whose model file is missing while it believes
otherwise. The second one is discovered weeks later, by a user complaining that
they keep being talked over.

With no judge, the caller keeps its silence deadline. That is the point of an
advisory model here: one that answers "not finished" and is wrong leaves somebody
waiting for a reply that never comes, so silence has to be able to end a turn by
itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import dials
from .mel import SAMPLE_RATE, log_mel
from .turn import MODEL_FILE, WINDOW_SAMPLES, SmartTurn

__all__ = [
    "MODEL_FILE",
    "SAMPLE_RATE",
    "WINDOW_SAMPLES",
    "SmartTurn",
    "Turn",
    "build_turn",
    "log_mel",
]

ENGINES = ("smart-turn", "none")


@dataclass(frozen=True)
class Turn:
    """What will judge a finished turn, and whether it is what was asked for."""

    engine: str
    fallback: bool
    reason: str
    judge: Any

    def ready(self) -> bool:
        """Whether a judgement is available at all."""
        return self.judge is not None and bool(self.judge.ready())

    def verdict(self, samples) -> dict | None:
        """``{"complete": bool, "prob": float}``, or None when there is no verdict.

        A judge that raises is treated as a judge that is not there. This runs
        between somebody finishing a sentence and a reply being produced, so an
        exception on this path replaces the reply with an error message, and "no
        verdict" is a perfectly good answer that the caller already handles.
        """
        if self.judge is None:
            return None
        try:
            return self.judge.judge(samples)
        except Exception:  # noqa: BLE001 - no verdict is an answer, a crash is not
            return None


def build_turn(enabled: bool | None = None, *, model_path: str | None = None) -> Turn:
    """Choose a judge, falling back visibly when it cannot run.

    Switching the model off is not a fallback. A host that asked for it gets
    ``engine="none"`` with no reason, because reporting "fell back" for a setting
    that is doing exactly what it was told is how a real fallback stops being
    read.
    """
    wanted = bool(dials()["smart_turn"] if enabled is None else enabled)
    if not wanted:
        return Turn("none", False, "", None)
    judge = SmartTurn(model_path)
    if judge.ready():
        return Turn("smart-turn", False, "", judge)
    return Turn(
        "none",
        True,
        f"no endpoint model at {judge.path}; a silence deadline has to end turns",
        None,
    )
