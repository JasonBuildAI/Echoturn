"""A scripted model and a scripted voice, for the pipeline tests."""
from __future__ import annotations

import threading
import time


def wav(marker: int = 1, size: int = 8) -> bytes:
    """Stand-in audio. Nothing in the pipeline looks inside it."""
    return b"RIFF" + bytes([marker]) * size


class FakeLLM:
    """Yields the pieces it was given, with an optional delay between them."""

    def __init__(self, pieces, *, delay: float = 0.0) -> None:
        self.pieces = list(pieces)
        self.delay = delay
        self.prompts: list[list[dict]] = []
        self.calls = 0

    def stream(self, messages):
        self.calls += 1
        self.prompts.append(list(messages))
        for piece in self.pieces:
            if self.delay:
                time.sleep(self.delay)
            yield piece


class BrokenLLM:
    """Fails the way a provider fails: with something fit only for a log."""

    def __init__(self, exc: BaseException | None = None) -> None:
        self.exc = exc or RuntimeError("/srv/internal/path failed")

    def stream(self, messages):
        raise self.exc
        yield  # pragma: no cover - makes this a generator


class FakeTTS:
    """One piece per chunk, with per-call delays, recording what it was asked.

    ``delays`` is consumed in call order, and calls are numbered in the order
    they arrive, which is the order the pipeline submitted them. That is what
    lets a test make the second chunk finish before the first.

    ``fail_on`` fails specific *calls* rather than specific texts, which is what
    makes the retry testable: the pipeline re-sends the same text, so a call that
    fails once and succeeds on the next is "a rate limit that cleared", and
    ``fail_all`` is "a provider that is simply down". Calls are numbered in the
    order they arrive and chunks are synthesised in parallel, so a call index is
    only a reliable way to name a chunk when the test has one chunk - or when it
    wants *any* chunk to fail. ``fail_containing`` names a chunk by its text and
    is what a test wants when one specific message has to stay silent however the
    retry lands.
    """

    def __init__(
        self, *, delays=(), fail_on=(), fail_all=False, fail_containing=None
    ) -> None:
        self.delays = list(delays)
        self.fail_on = set(fail_on)
        self.fail_all = fail_all
        self.fail_containing = fail_containing
        self.texts: list[str] = []
        self.completed: list[int] = []
        self.streamed = 0
        self.whole = 0
        self._lock = threading.Lock()

    def synth(self, text: str, *, emotion=None, voice=None):
        with self._lock:
            self.whole += 1
        return wav(len(text))

    def synth_stream(
        self, text: str, *, emotion=None, voice=None, chunk_cb=None
    ):
        with self._lock:
            index = self.streamed
            self.streamed += 1
            self.texts.append(text)
            delay = self.delays[index] if index < len(self.delays) else 0.0
            fail = (
                self.fail_all
                or index in self.fail_on
                or (
                    self.fail_containing is not None
                    and self.fail_containing in str(text)
                )
            )
        if delay:
            time.sleep(delay)
        if fail:
            raise RuntimeError("the voice service said no")
        audio = wav(index + 1)
        if chunk_cb is None:
            with self._lock:
                self.completed.append(index)
            return audio
        chunk_cb(audio)
        with self._lock:
            self.completed.append(index)
        return None


class HalfSpeakingTTS:
    """A provider that drops mid-stream: some audio out, then a failure.

    The shape matters more than the numbers here. A chunk that got part of a
    sentence out must not be re-synthesised - the beginning would be said twice -
    so this is what a test needs to tell "produced nothing" apart from "produced
    something and then broke".
    """

    def __init__(self) -> None:
        self.calls = 0
        self._lock = threading.Lock()

    def synth(self, text: str, *, emotion=None, voice=None):
        return wav(1)

    def synth_stream(self, text: str, *, emotion=None, voice=None, chunk_cb=None):
        with self._lock:
            self.calls += 1
        if chunk_cb is not None:
            chunk_cb(wav(1))
        raise RuntimeError("the connection dropped mid-sentence")


class AbandonedTTS:
    """A provider that fails at the same moment the caller gives up.

    Written to pin one thing: a turn nobody is listening to does not get a second
    synthesis request. The cancel is set from inside the failure rather than from
    the test, so the order of the two is not a race.
    """

    def __init__(self, cancel: threading.Event) -> None:
        self.cancel = cancel
        self.calls = 0
        self._lock = threading.Lock()

    def synth(self, text: str, *, emotion=None, voice=None):
        return wav(1)

    def synth_stream(self, text: str, *, emotion=None, voice=None, chunk_cb=None):
        with self._lock:
            self.calls += 1
        self.cancel.set()
        raise RuntimeError("the voice service said no")


class SilentTTS:
    """A provider that produces no audio at all, without failing."""

    def synth(self, text: str, *, emotion=None, voice=None):
        return b""

    def synth_stream(self, text, *, emotion=None, voice=None, chunk_cb=None):
        if chunk_cb is None:
            return b""
        return None


class FakeASR:
    """A recogniser that answers with what it was told, and records the ask."""

    def __init__(self, text: str = "hello") -> None:
        self.text = text
        self.calls: list[dict] = []

    def transcribe(self, audio, *, sample_rate, fmt, lang):
        self.calls.append(
            {
                "bytes": len(audio),
                "sample_rate": sample_rate,
                "fmt": fmt,
                "lang": lang,
            }
        )
        return self.text
