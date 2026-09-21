"""A speech detector that needs no model.

It measures one thing - how loud each block is - and reports how long the audio
stayed above a level. That is enough to separate "a knock" from "a sentence" in a
quiet room, and it is a useful second opinion everywhere else.

What it cannot do is separate "somebody talking" from "somebody playing music",
and its level is absolute, so a noisy room raises it and a quiet microphone
lowers it. That is a property of the method rather than of this implementation,
which is why the model is the default and this runs when the model is missing, or
when a host has decided a model is not worth the download.

The level below is a starting point and not a measured value - the one number in
this package that says so out loud. About -34 dBFS, which sits under
conversational speech recorded at a normal distance and above the self noise of
most microphones. A room with a fan in it needs a different number, and a host
that has measured its own room should pass one.
"""
from __future__ import annotations

from .segments import BLOCK_MS, speech_ms

SAMPLE_RATE = 16000
DEFAULT_FLOOR = 0.02


class EnergyVad:
    """Speech length from loudness alone."""

    engine = "energy"

    def __init__(
        self,
        floor: float = DEFAULT_FLOOR,
        *,
        sample_rate: int = SAMPLE_RATE,
        block_ms: float = BLOCK_MS,
    ) -> None:
        self.floor = float(floor)
        self.sample_rate = int(sample_rate)
        self.block_ms = float(block_ms)

    @property
    def block(self) -> int:
        """Samples in one analysis block."""
        return max(1, int(self.sample_rate * self.block_ms / 1000.0))

    def levels(self, samples) -> list[float]:
        """Root-mean-square level of every block, in the units it was given.

        A partial block at the end is measured as it is rather than dropped:
        dropping it would quietly lose the last few milliseconds of a word, which
        is exactly the part a caller is gating on.
        """
        np = self._numpy()
        x = np.asarray(samples, dtype=np.float64).reshape(-1)
        block = self.block
        ends = range(0, len(x), block)
        return [
            float(np.sqrt(float((x[start:start + block] ** 2).mean())))
            for start in ends
            if len(x[start:start + block])
        ]

    def report(self, samples) -> dict:
        """Speech length and how loud it was."""
        levels = self.levels(samples)
        flags = [1.0 if level > self.floor else 0.0 for level in levels]
        loud = [level for level in levels if level > self.floor]
        return {
            "engine": self.engine,
            "speech_ms": speech_ms(flags, block_ms=self.block_ms),
            "level": float(sum(loud) / len(loud)) if loud else 0.0,
        }

    @staticmethod
    def _numpy():
        from ..audio._dsp import numpy

        return numpy()
