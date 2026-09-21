"""Decide when buffered text is long enough to send to synthesis.

One sentence per request would be the obvious choice and it is the wrong one.
Every synthesis request sees its text in isolation, with no context from the
previous request, so it starts its own intonation from scratch and the joins
between sentences become audible seams - the thing that makes a voice sound like
a machine reading a list. Buffering a few sentences lets the model see a phrase
and carry the tone across the join.

The counter-pressure is first-sound latency, which is why the first chunk has its
own, smaller threshold. Listeners judge speed almost entirely on the first sound;
after that, prosody matters more than another hundred milliseconds.

This class holds no defaults. The numbers are measured values and they live in
the knob table, so a host can retune them without touching code.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkPolicy:
    """Character thresholds for one synthesis chunk."""

    chunk_chars: int
    chunk_min: int
    first_chars: int
    first_min: int
    first_call_chars: int
    first_call_min: int
    terminators: str = "。！？!?"

    def should_flush(
        self, buffer: str, *, first: bool = False, call: bool = False
    ) -> bool:
        """Whether ``buffer`` should be sent now.

        Two ways to qualify: long enough regardless of punctuation, or short
        enough to be waiting but sitting on a finished sentence. The second rule
        is what keeps a two-word reply from waiting for a character count it will
        never reach.

        ``first`` selects the fast path for the opening chunk and ``call``
        selects the tighter variant used inside a live call, where a turn is
        usually one or two sentences and the first sound is nearly all of the
        perceived speed.
        """
        text = str(buffer or "")
        if first:
            head_chars = self.first_call_chars if call else self.first_chars
            head_min = self.first_call_min if call else self.first_min
            if len(text) >= head_chars:
                return True
            return len(text) >= head_min and self._ends_sentence(text)
        if len(text) >= self.chunk_chars:
            return True
        return len(text) >= self.chunk_min and self._ends_sentence(text)

    def _ends_sentence(self, text: str) -> bool:
        return text.rstrip()[-1:] in self.terminators
