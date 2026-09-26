import asyncio
import json
import threading
import time

import pytest

pytest.importorskip("starlette")

from echoturn import events
from echoturn.errors import UNEXPECTED_MESSAGE, ProviderError
from echoturn.integrations.starlette import LiveTurns, sse_response, sse_stream


def drain(stream, cancel=None, **kwargs):
    """Run one stream to the end and return the decoded events.

    Comment frames - the heartbeat that keeps an idle connection alive - are
    counted and dropped, which is what a client does with them.
    """
    cancel = cancel or threading.Event()
    comments = []

    async def collect():
        out = []
        async for frame in sse_stream(stream, cancel, **kwargs):
            if frame.startswith(":"):
                comments.append(frame)
                continue
            assert frame.startswith("data: ")
            assert frame.endswith("\n\n")
            out.append(json.loads(frame[len("data: "):-2]))
        return out

    return asyncio.run(collect()), cancel


def test_events_reach_the_client_in_the_order_they_were_produced():
    def stream():
        yield events.ack("m1")
        for idx in range(50):
            yield events.sentence(idx, f"line {idx}")
        yield events.done("all of it")

    got, _ = drain(stream())
    assert [event["type"] for event in got] == (
        ["ack"] + ["sentence"] * 50 + ["done"]
    )
    assert [event["i"] for event in got[1:51]] == list(range(50))


def test_a_failing_stream_ends_with_a_line_a_person_can_read():
    def stream():
        yield events.ack("m1")
        raise ValueError("/home/someone/secret.py blew up")

    got, _ = drain(stream())
    assert got[-1] == {"type": "error", "error": UNEXPECTED_MESSAGE}
    assert "secret" not in json.dumps(got)


def test_a_provider_error_keeps_the_wording_it_was_written_with():
    def stream():
        yield from ()
        raise ProviderError("the voice service is unavailable", detail="HTTP 503")

    got, _ = drain(stream())
    assert got == [{"type": "error", "error": "the voice service is unavailable"}]


def test_the_loop_keeps_running_while_the_turn_is_quiet():
    """The whole reason the bridge exists: waiting must not hold a thread."""

    def stream():
        yield events.ack("m1")
        time.sleep(0.3)
        yield events.done("hi")

    async def main():
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        task = asyncio.create_task(ticker())
        try:
            async for _frame in sse_stream(stream(), threading.Event()):
                pass
        finally:
            task.cancel()
        return ticks

    assert asyncio.run(main()) > 10


def test_a_client_that_leaves_stops_the_turn():
    """Closing the response is the disconnect signal, and it must cancel."""
    disconnected = threading.Event()
    started = threading.Event()

    def stream():
        yield events.ack("m1")
        started.set()
        time.sleep(5.0)
        yield events.done("never sent")

    async def main():
        response = sse_stream(stream(), disconnected)
        frame = await response.__anext__()
        assert "ack" in frame
        await response.aclose()

    asyncio.run(main())
    assert started.is_set()
    assert disconnected.is_set()


def test_a_quiet_stream_is_kept_alive_without_being_told_anything(monkeypatch):
    """A turn is quiet for seconds at a time, and an idle connection is dropped.

    The frame carries no event, so a client that reads ``data:`` lines never
    sees one - which is the whole reason a comment is safe to send.
    """
    monkeypatch.setattr("echoturn.integrations.starlette.HEARTBEAT_SEC", 0.05)

    def stream():
        yield events.ack("m1")
        time.sleep(0.2)
        yield events.done("hi")

    cancel = threading.Event()
    frames = []

    async def collect():
        async for frame in sse_stream(stream(), cancel):
            frames.append(frame)

    asyncio.run(collect())
    beats = [frame for frame in frames if frame.startswith(":")]
    assert beats, "a quiet stretch sends something to hold the connection"
    assert all(frame.startswith(":") and "data:" not in frame for frame in beats)
    assert [frame for frame in frames if frame.startswith("data: ")] == [
        events.encode(events.ack("m1")),
        events.encode(events.done("hi")),
    ], "and the events are untouched, in order"


def test_a_response_carries_the_headers_that_stop_proxy_buffering():
    response = sse_response(iter(()), threading.Event())
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"


def test_a_newer_turn_stops_the_one_under_the_same_key():
    live = LiveTurns()
    first, second = threading.Event(), threading.Event()
    live.begin("user-1", first)
    live.begin("user-1", second)
    assert first.is_set()
    assert second.is_set() is False
    assert len(live) == 1


def test_a_finished_turn_does_not_forget_its_replacement():
    live = LiveTurns()
    first, second = threading.Event(), threading.Event()
    live.begin("user-1", first)
    live.begin("user-1", second)
    live.end("user-1", first)
    assert live.is_live("user-1") is True
    live.end("user-1", second)
    assert live.is_live("user-1") is False


def test_hanging_up_stops_the_live_turn_and_says_whether_it_did():
    live = LiveTurns()
    cancel = threading.Event()
    assert live.stop("user-1") is False
    live.begin("user-1", cancel)
    assert live.stop("user-1") is True
    assert cancel.is_set()


def test_two_keys_do_not_interfere():
    live = LiveTurns()
    one, two = threading.Event(), threading.Event()
    live.begin("user-1", one)
    live.begin("user-2", two)
    assert one.is_set() is False
    assert len(live) == 2
