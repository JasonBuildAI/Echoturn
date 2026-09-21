"""Change speaking rate without changing pitch.

Speed is one of the few dials that changes how a voice feels without changing who
it is, so it is exposed - but the way a naive implementation would do it (dropping
or repeating samples) also transposes the voice, which is worse than the problem
it solves. Time stretching keeps the pitch centre where it was.
"""
from __future__ import annotations

from . import _phase
from ._dsp import numpy

MIN_RATE = 0.5
MAX_RATE = 2.0
PCM_SCALE = 32768.0


def clamp_rate(rate: float, default: float = 1.0) -> float:
    """Keep a configured speed inside the range that still sounds like a person."""
    value = float(rate)
    return value if MIN_RATE <= value <= MAX_RATE else default


def time_stretch(pcm: bytes, rate: float) -> bytes:
    """Return ``pcm`` played at ``rate`` times its original speed.

    ``rate`` above one is faster. A rate outside the supported range is rejected
    rather than clamped silently, because the caller that asked for it should
    find out that it did not get what it asked for. The result is exactly
    ``1 / rate`` of the input length, rounded, so a caller can pre-announce it.
    """
    effective = float(rate)
    if not MIN_RATE <= effective <= MAX_RATE:
        raise ValueError(f"rate must be between {MIN_RATE} and {MAX_RATE}")
    raw = bytes(pcm or b"")
    if effective == 1.0:
        return raw
    np = numpy()
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float64) / PCM_SCALE
    stretched = _phase.stretch(np, samples, effective)
    wanted = max(1, int(round(len(raw) // 2 / effective)))
    stretched = _phase.fit_length(np, stretched, wanted)
    clipped = np.clip(stretched * PCM_SCALE, -PCM_SCALE, PCM_SCALE - 1)
    return clipped.astype("<i2").tobytes()
