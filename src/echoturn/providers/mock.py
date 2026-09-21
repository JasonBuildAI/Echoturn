"""Providers that answer without a network, so the pipeline can be run offline.

These exist for two jobs and it is worth keeping both in mind. The first is
development: every part of this package can be exercised, and every timing
measured, with no key, no account and no bill. The second is tests: this is the
only provider whose output is byte-for-byte reproducible, which is what makes a
"the event stream did not change" test possible at all.

They are also honest about being fake, which is the one property that matters
most. The voice is a beep, not speech. The transcript says it is a mock
transcript. A stand-in that sounds convincing is a stand-in somebody will ship
by accident and then spend a day debugging what turns out to be a hard-coded
string.
"""
from __future__ import annotations

import math
import struct
from collections.abc import Iterable, Iterator, Mapping

from ..audio.wav import pcm16_to_wav, wav_seconds
from .base import WholeClipTTS

# The rate a beep of this kind is generated at. It is also the rate speech
# models are usually fed, so a mock clip and a real one are interchangeable for
# everything downstream.
SAMPLE_RATE = 16000
# Peak amplitude, well below the clipping point: the pipeline's own gain staging
# should be what a test measures, not this generator's.
AMPLITUDE = 9000
# Roughly a syllable per character. The floor and ceiling keep a two-word reply
# from being inaudible and a paragraph from holding the turn open for a minute.
SECONDS_PER_CHAR = 0.11
MIN_SECONDS = 0.9
MAX_SECONDS = 6.0
# A little vibrato, so the beep does not sit exactly on one frequency - a pure
# tone is an unusually easy signal for anything downstream to measure.
VIBRATO_HZ = 5.0
VIBRATO_DEPTH = 0.03
# No sound arrives instantly or stops dead; both would read as a click.
ATTACK_PER_SECOND = 8.0
RELEASE_SECONDS = 0.25
# One base frequency per emotion tag, so that a host can hear for itself that the
# emotion it passed through actually arrived. Tags that are not listed get the
# middle of the range.
TONES: dict[str, int] = {
    "calm": 200,
    "sad": 170,
    "guarded": 190,
    "warm": 210,
    "tender": 240,
    "bright": 300,
    "playful": 330,
    "flustered": 360,
}
DEFAULT_TONE = 220


class MockTTS(WholeClipTTS):
    """A beep whose length follows the text and whose pitch follows the emotion."""

    provider = "mock"

    def synth(
        self, text: str, *, emotion: str | None = None, voice: str | None = None
    ) -> bytes:
        base = TONES.get((emotion or "").strip().lower(), DEFAULT_TONE)
        seconds = min(
            MAX_SECONDS, max(MIN_SECONDS, len(str(text or "")) * SECONDS_PER_CHAR)
        )
        count = int(SAMPLE_RATE * seconds)
        samples = bytearray()
        for i in range(count):
            t = i / SAMPLE_RATE
            attack = min(1.0, t * ATTACK_PER_SECOND)
            release = max(
                0.0, 1.0 - max(0.0, t - seconds + RELEASE_SECONDS) / RELEASE_SECONDS
            )
            hz = base * (1.0 + VIBRATO_DEPTH * math.sin(2 * math.pi * VIBRATO_HZ * t))
            value = int(AMPLITUDE * attack * release * math.sin(2 * math.pi * hz * t))
            samples += struct.pack("<h", max(-32768, min(32767, value)))
        return pcm16_to_wav(bytes(samples), SAMPLE_RATE)


class MockASR:
    """A transcript that cannot be mistaken for a real one.

    It reports what it was given rather than inventing words, because a fake
    sentence travelling through the rest of the pipeline produces a conversation
    that looks like it works.
    """

    provider = "mock"

    def transcribe(
        self,
        audio: bytes,
        *,
        sample_rate: int = 16000,
        fmt: str = "wav",
        lang: str = "auto",
    ) -> str:
        return f"[mock transcript of {wav_seconds(audio):.1f}s of {fmt}]"


class MockLLM:
    """A reply built from the prompt, delivered in pieces like a real stream."""

    provider = "mock"
    # Small enough that a sentence boundary lands inside a piece now and then,
    # which is the case a naive consumer of the stream gets wrong.
    PIECE_CHARS = 8

    def stream(self, messages: Iterable[Mapping[str, str]]) -> Iterator[str]:
        prompt = self._last_user_message(messages)
        reply = f"[mock reply] {prompt}".strip()
        for start in range(0, len(reply), self.PIECE_CHARS):
            yield reply[start:start + self.PIECE_CHARS]

    @staticmethod
    def _last_user_message(messages: Iterable[Mapping[str, str]]) -> str:
        found = ""
        for message in messages or ():
            if str(message.get("role") or "") == "user":
                found = str(message.get("content") or "")
        return found
