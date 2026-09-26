"""Serving a turn as Server-Sent Events, from a synchronous event stream.

The bridge exists for one reason, and it is a performance reason. Starlette
iterates a *synchronous* generator with ``anyio.to_thread.run_sync`` - one call
to ``next()`` at a time, each on a worker thread from a pool that defaults to
forty. The pipeline's generator blocks waiting for the model and for synthesis,
so a single turn would hold one of those forty threads for its whole lifetime.
Forty people talking at once and the forty-first person's every request - typing,
polling, anything - queues behind them. It reads as "when more than a handful of
people use it, everybody waits".

So the synchronous stream is handed to a thread of its own, which pushes events
into an asyncio queue. The event loop is woken only when there is something to
send and holds no thread while it waits.

The cancellation corner is the part worth reading twice:

- ``cancel`` is the caller's :class:`threading.Event`, the same object it handed
  to :func:`echoturn.pipeline.run_turn`. When the client goes away, this module
  can only set it and wait: closing the generator from here would touch it from a
  thread that does not own it while that owner may be inside ``next()``, which
  raises "generator already executing".
- The generator notices within one poll interval (200 ms) and stops. Any
  ``aborted`` event it produces then has nobody left to receive it, which is
  fine and must not be turned into "do not send it": the other cancellation path,
  a newer turn replacing this one, still has a listener.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections.abc import Iterable, Mapping
from typing import Any

from starlette.responses import StreamingResponse

from ..errors import safe_message
from ..events import encode, error

__all__ = ["LiveTurns", "sse_response", "sse_stream"]

log = logging.getLogger("echoturn.integrations.starlette")

# Proxies buffer responses by default, which turns a stream into a reply that
# arrives all at once at the end. These headers are what stops that.
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

# How long the stream may say nothing before a comment frame goes out. A turn is
# genuinely quiet for seconds at a time - the model is still writing, a synthesis
# request is still out - and a connection that says nothing for long enough is
# dropped by proxies, mobile networks and load balancers, all of which report it
# as a failure of the turn. A comment frame is not an event: the client's frame
# parser looks for ``data:`` lines and skips this one, which is exactly why it is
# safe to send without agreeing on a new event type.
HEARTBEAT_SEC = 5.0
# A frame with no event in it. SSE reserves the colon for exactly this.
HEARTBEAT = ": keep-alive\n\n"


class LiveTurns:
    """One live turn per key, with the newest one winning.

    Two turns writing the same conversation interleave into something nobody can
    read: the reply to the first question arrives under the second one. Clients
    are expected to stop the previous turn themselves, and this is the server
    side of the same promise, because a client that gets it wrong should not be
    able to corrupt the record.

    The key is whatever the host considers one conversation - one per user, in
    the demo. Nothing here knows what a key means.
    """

    def __init__(self) -> None:
        self._live: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def begin(self, key: str, cancel: threading.Event) -> None:
        """Register a turn, stopping whatever was running under this key."""
        with self._lock:
            previous = self._live.get(str(key))
            self._live[str(key)] = cancel
        if previous is not None and previous is not cancel:
            previous.set()

    def end(self, key: str, cancel: threading.Event) -> None:
        """Forget a turn, but only if the live one is still this one.

        Without the ownership check a finished turn would remove its
        replacement, and a third turn would then run alongside the second.
        """
        with self._lock:
            if self._live.get(str(key)) is cancel:
                self._live.pop(str(key), None)

    def stop(self, key: str) -> bool:
        """Stop the live turn for a key, if there is one. For a hang-up button."""
        with self._lock:
            cancel = self._live.get(str(key))
        if cancel is None:
            return False
        cancel.set()
        return True

    def is_live(self, key: str) -> bool:
        """Whether a turn is registered for this key. It may be finishing."""
        with self._lock:
            return str(key) in self._live

    def __len__(self) -> int:
        with self._lock:
            return len(self._live)


async def sse_stream(
    events: Iterable[Mapping[str, Any]],
    cancel: threading.Event,
    *,
    key: str = "",
    live: LiveTurns | None = None,
) -> Any:
    """Yield SSE frames for a synchronous event stream.

    ``events`` is consumed on a thread of its own; see the module docstring for
    why that is not optional.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    finished = object()

    def push(item: Any) -> bool:
        """Hand one item to the event loop. False once the loop is gone."""
        # The coroutine is built first and explicitly closed if it never gets
        # scheduled. A loop that has already stopped makes
        # ``run_coroutine_threadsafe`` raise immediately, and the never-awaited
        # coroutine would otherwise surface later as a RuntimeWarning - on a
        # path that is entirely normal.
        coro = queue.put(item)
        try:
            asyncio.run_coroutine_threadsafe(coro, loop).result()
            return True
        except Exception:  # noqa: BLE001 - the loop is gone; nothing to report
            coro.close()
            return False

    def pump() -> None:
        try:
            for event in events:
                if not push(event):
                    break
        except Exception as exc:  # noqa: BLE001 - the only way out of this thread
            log.exception("the turn's event stream failed")
            push(error(safe_message(exc)))
        finally:
            push(finished)
            # Safe here and only here: this thread holds the generator and is not
            # inside next() right now. Closing it delivers GeneratorExit to the
            # pipeline's finally blocks, which is what releases unstarted work.
            close = getattr(events, "close", None)
            if close is not None:
                # Already closed, or not a generator at all: either way there is
                # nothing left to release and nothing useful to report.
                with contextlib.suppress(Exception):
                    close()

    threading.Thread(target=pump, name="echoturn-sse", daemon=True).start()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SEC)
            except asyncio.TimeoutError:
                # Nothing to send, and that is the point: this frame exists so
                # that the connection is not idle, not to say anything.
                yield HEARTBEAT
                continue
            if event is finished:
                break
            yield encode(event)
    finally:
        cancel.set()
        if live is not None and key:
            live.end(key, cancel)


def sse_response(
    events: Iterable[Mapping[str, Any]],
    cancel: threading.Event,
    *,
    key: str = "",
    live: LiveTurns | None = None,
    headers: Mapping[str, str] | None = None,
) -> StreamingResponse:
    """A streaming HTTP response for one turn.

    ``cancel`` must be the same object the turn was started with. There is no
    default on purpose: a response that invents its own Event looks correct and
    silently stops being able to stop anything.
    """
    merged = dict(SSE_HEADERS)
    merged.update(headers or {})
    return StreamingResponse(
        sse_stream(events, cancel, key=key, live=live),
        media_type="text/event-stream",
        headers=merged,
    )
