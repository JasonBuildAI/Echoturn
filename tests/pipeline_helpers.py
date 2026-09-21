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
    """

    def __init__(self, *, delays=(), fail_on=()) -> None:
        self.delays = list(delays)
        self.fail_on = set(fail_on)
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
            fail = index in self.fail_on
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


class SilentTTS:
    """A provider that produces no audio at all, without failing."""

    def synth(self, text: str, *, emotion=None, voice=None):
        return b""

    def synth_stream(self, text, *, emotion=None, voice=None, chunk_cb=None):
        if chunk_cb is None:
            return b""
        return None
