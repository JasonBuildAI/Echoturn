"""The events one turn can emit, and their wire shape.

A turn is a stream of plain dictionaries rather than a callback API, because the
consumer is almost always something that has to send them somewhere: an SSE
response, a websocket, a queue. A stream is also the only shape that survives the
three things a turn does at once - the model is still writing, synthesis is
finished for chunk three, and chunk two is still coming.

The names and fields below are a contract. Anything that speaks this protocol can
be driven by anything that emits it, and the client shipped in ``clients/`` is
written against exactly these keys:

``ack``
    The caller's message is committed and this is its id. It goes out before any
    money is spent, so a client can tell "never arrived" from "arrived and was
    interrupted" - without it both look like a failed request, and the user
    retypes a message that was received the first time.
``sentence``
    One speakable sentence, with ``i`` = which of the turn's messages it belongs
    to. This is the subtitle stream: it arrives before the audio does.
``audio``
    One WAV chunk as base64, with ``idx`` = its position in the turn and ``i`` =
    the message it belongs to. ``idx`` is what makes playback ordered; the
    arrival order of audio events is not sorted, and never will be.
``sink``
    Where the audio is meant to come out, and anything the host wants said about
    that. Sent early, because deciding it can be slow and it must not delay the
    reply.
``aborted``
    The turn was cancelled or replaced. Terminal.
``done``
    The whole reply as text, plus what the turn measured. Terminal.
``error``
    The turn failed. ``error`` is safe to show to a person; the exception text is
    not, and belongs in the host's log. Terminal.
"""
from __future__ import annotations

import base64
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

__all__ = [
    "AUDIO_MIME",
    "EVENT_TYPES",
    "SUPERSEDED",
    "TERMINAL",
    "aborted",
    "ack",
    "audio",
    "done",
    "encode",
    "error",
    "iter_encoded",
    "sentence",
    "sink",
]

EVENT_TYPES = ("ack", "sentence", "audio", "sink", "aborted", "done", "error")

# Exactly one of these ends a stream, and a client that has seen one should stop
# expecting anything else. Three endings rather than one because "she finished",
# "we stopped her" and "it broke" need different words on screen.
TERMINAL = ("aborted", "done", "error")

# WAV rather than raw samples: the browser decodes it without being told the
# sample rate, the channel count or the encoding, and those three are exactly
# what a speech provider is free to pick.
AUDIO_MIME = "audio/wav"


def ack(message_id: str) -> dict:
    """The caller's message is committed under this id."""
    return {"type": "ack", "id": str(message_id)}


def sentence(index: int, text: str) -> dict:
    """One speakable sentence of message ``index``."""
    return {"type": "sentence", "i": int(index), "text": str(text)}


def audio(idx: int, message: int, wav: bytes) -> dict:
    """One chunk of audio, numbered by its position in the turn.

    ``idx`` is the ordering key. It is not a hint: chunks are synthesised in
    parallel and finish out of order, so a client that plays them as they arrive
    plays two sentences interleaved.
    """
    return {
        "type": "audio",
        "idx": int(idx),
        "i": int(message),
        "mime": AUDIO_MIME,
        "data": base64.b64encode(wav).decode("ascii"),
    }


def sink(audio_sink: str = "browser", notice: str = "") -> dict:
    """Where the audio comes out. ``notice`` is shown to a person as-is."""
    return {"type": "sink", "audio_sink": str(audio_sink), "notice": str(notice)}


def aborted(reason: str) -> dict:
    """The turn was stopped.

    ``reason`` is a short word for the client to choose its wording with. The one
    this package emits is :data:`SUPERSEDED`; a host that cancels for its own
    reasons passes its own word, and there is no vocabulary to keep in step.
    """
    return {"type": "aborted", "reason": str(reason)}


def done(
    reply: str,
    *,
    timings: Mapping[str, Any] | None = None,
    warnings: Sequence[str] = (),
    extra: Mapping[str, Any] | None = None,
) -> dict:
    """The finished turn: the text, what it cost in time, and what went wrong.

    ``warnings`` is not the place for things that broke the turn - those are
    ``error`` events. It is for the parts that worked badly, above all a chunk of
    speech that failed to synthesise: the text of that sentence is still here and
    can still be read, and the caller deserves to know it was never spoken.
    """
    event: dict = {
        "type": "done",
        "reply": str(reply),
        "timings": dict(timings or {}),
        "warnings": [str(item) for item in warnings],
    }
    if extra:
        # Host fields the pipeline does not interpret, kept in one place so they
        # cannot collide with the contract above by accident.
        event["extra"] = dict(extra)
    return event


def error(message: str) -> dict:
    """The turn failed. ``message`` must be safe to put in front of a person."""
    return {"type": "error", "error": str(message)}


# Why this package stops a turn: something newer replaced it. A client that
# disconnected causes the same thing, and the caller cannot tell the two apart -
# both are "this turn is no longer wanted".
SUPERSEDED = "superseded"


def encode(event: Mapping[str, Any]) -> str:
    """One event as an SSE frame.

    Text is not escaped to ASCII. Every hop between here and a browser is UTF-8,
    and ``\\uXXXX`` escapes would triple the size of a Chinese reply for no
    benefit anybody can observe.
    """
    return "data: " + json.dumps(dict(event), ensure_ascii=False) + "\n\n"


def iter_encoded(events: Iterable[Mapping[str, Any]]) -> Iterable[str]:
    """Encode a stream of events without holding it in memory."""
    for event in events:
        yield encode(event)
