"""The conversation window a host keeps, and one implementation of it.

A prompt has to carry recent context or the reply reads like a first message
every time. That is the whole job of this module, and the deliberate limit of it:
it holds what was said, it caps how much of that is sent, and it reopens after a
quiet gap. It is not memory. There is no extraction, no summary, no retrieval,
and nothing here that could be mistaken for remembering something from a hundred
turns ago - because a window that is only ever read cannot do that, and a host
that wants it has to bring a real system for it.

Two sizes, and they are different on purpose: what is *kept* per conversation is
larger than what is *sent*. Keeping a little more than is sent means the window
can be trimmed without losing the immediately preceding turns, and it bounds the
memory of a long-running process without bounding what the model sees.

The idle gap is the third moving part. After a long silence the window reopens
empty, so the model starts fresh instead of reading a conversation with a
five-hour hole in it and answering the wrong half. It affects this and nothing
else: what was said is still what was said, and a host that stores a transcript
elsewhere is not asked to delete any of it.
"""
from __future__ import annotations

import threading
import time
from typing import Protocol, runtime_checkable

from .config import dials

__all__ = [
    "KEEP_MESSAGES",
    "WINDOW_MESSAGES",
    "InMemoryStore",
    "TranscriptStore",
]

# What a turn sends to the model: the last dozen exchanges, which is well past
# the point where a conversation needs them and well short of a prompt whose
# cost per turn grows without limit.
WINDOW_MESSAGES = 24

# What a conversation keeps, so that trimming to the window does not have to be
# exact and the turn before the window is still there for a host that asks.
KEEP_MESSAGES = 64


@runtime_checkable
class TranscriptStore(Protocol):
    """Recent messages per conversation: the two calls the pipeline needs.

    A protocol rather than a base class, because a host already has somewhere
    this belongs - a table, a cache, a session object - and making it inherit
    from us to be accepted is the coupling this package exists to avoid.

    ``key`` is whatever the host calls one conversation. Nothing here interprets
    it.
    """

    def window(self, key: str) -> list[dict]:
        """The messages to send as context, oldest first."""

    def append(self, key: str, role: str, text: str) -> None:
        """Add one message to the conversation."""


class InMemoryStore:
    """A reference :class:`TranscriptStore`, in a dictionary.

    Suitable for a single process and a demo, and honest about it: it is lost on
    restart, it is not shared between workers, and it grows with the number of
    conversations that are currently in use. A host serving more than a demo
    writes the twenty lines that talk to its own storage instead.
    """

    def __init__(
        self,
        *,
        window: int = WINDOW_MESSAGES,
        keep: int = KEEP_MESSAGES,
        idle_sec: int | None = None,
        clock=time.time,
    ) -> None:
        self.window_size = max(1, int(window))
        self.keep = max(self.window_size, int(keep))
        # ``None`` means "read the setting when it is needed", so an operator who
        # changes the gap does not have to restart anything.
        self._idle_sec = idle_sec
        self._clock = clock
        self._messages: dict[str, list[dict]] = {}
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def idle_sec(self) -> int:
        """How long a quiet gap reopens the window for."""
        if self._idle_sec is not None:
            return int(self._idle_sec)
        return int(dials()["idle_split_sec"])

    def window(self, key: str) -> list[dict]:
        """The messages to send, oldest first. Reading counts as activity."""
        with self._lock:
            self._reopen_if_stale(key)
            self._seen[key] = self._clock()
            kept = self._messages.get(str(key), ())
            return [dict(message) for message in kept[-self.window_size :]]

    def append(self, key: str, role: str, text: str) -> None:
        """Add one message, keeping the retained history bounded."""
        with self._lock:
            self._reopen_if_stale(key)
            self._seen[key] = self._clock()
            kept = self._messages.setdefault(str(key), [])
            kept.append({"role": str(role), "content": str(text)})
            if len(kept) > self.keep:
                del kept[: len(kept) - self.keep]

    def clear(self, key: str) -> None:
        """Forget one conversation entirely."""
        with self._lock:
            self._messages.pop(str(key), None)
            self._seen.pop(str(key), None)

    def keys(self) -> list[str]:
        """The conversations currently being kept."""
        with self._lock:
            return sorted(self._messages)

    def _reopen_if_stale(self, key: str) -> None:
        """Drop the window when the last thing said was too long ago.

        Called before every read and every write, so there is exactly one place
        that decides what a gap means. Deciding it in two places - on read here,
        on write somewhere else - is how a conversation ends up half reopened.
        """
        key = str(key)
        seen = self._seen.get(key)
        if seen is None:
            return
        if self._clock() - seen > self.idle_sec():
            self._messages.pop(key, None)
            self._seen.pop(key, None)
