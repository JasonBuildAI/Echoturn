"""One turn, with generation, synthesis and delivery running at once.

The reason this is a module of its own, and not a function inside a route, is
that it is genuinely concurrent and that concurrency is the product. Three things
happen simultaneously:

* a producer thread reads the model's reply, cuts it into sentences and decides
  when enough text has accumulated to be worth a synthesis request;
* a shared pool synthesises those chunks, several at a time, so that chunk two is
  being fetched while chunk one is still being spoken;
* this generator only moves events out, and never makes anyone wait for anything
  it is not.

The design that was tried first - pull from the model in the main loop and hand
synthesis off to a pool - keeps generation and playback in series even though the
synthesis is asynchronous, because the main loop only returns to the audio when
the model is done. That version sounds like a walkie-talkie, and no amount of
pool size fixes it.

Two invariants hold this together, and both of them were bugs before they were
invariants:

1. Audio leaves strictly in chunk order. Synthesis finishes out of order by
   nature, so ordering is not left to timing: see :class:`_AudioOrder`.
2. ``done`` is the last event of a turn. Every submitted chunk is waited for
   before it is emitted, or a client would mark the turn complete while the last
   sentence is still arriving.

Cancellation has three exits - the caller's ``cancel`` flag, the consumer closing
the generator, and a failure - and all of them discard work that has not started,
within one poll interval of 200 ms.
"""
from __future__ import annotations

import atexit
import contextlib
import logging
import queue
import threading
import time
import uuid
from collections.abc import Iterator, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from .config import dials
from .errors import safe_message
from .events import SUPERSEDED, aborted, ack, audio, done, error, sentence, sink
from .protocols import LLMClient, TTSClient
from .text import (
    TEXT_STYLE,
    VOICE_STYLE,
    ChunkPolicy,
    clean_reply,
    iter_message_sentences,
    prepare_for_tts,
)

log = logging.getLogger("echoturn.pipeline")

# How long the event loop may go without looking up to check for a cancellation.
# This single number is the answer to "how quickly does she stop when I start
# talking": a barge-in is only audible as fast as this loop notices.
POLL_SEC = 0.2


class _AudioOrder:
    """Hands audio out strictly by chunk index, whatever order it finishes in.

    The subtle part, and the reason this is a class rather than an if: a chunk
    that streams is produced *over time*. It is normal for chunk one to still be
    emitting pieces while chunk zero has already finished. So "chunk zero is
    done" cannot mean "chunk one is complete" - if it did, every piece chunk one
    emitted afterwards would be queued as belonging to a future chunk and nothing
    would ever come to collect it. That failure sounds like the voice stopping
    mid-sentence, several seconds in.

    Hence two pieces of state: which chunks have finished, and which pieces have
    arrived. The next chunk is released only when it has finished *and* its
    pieces have been handed over.

    Handing over happens inside the lock. Two synthesis workers releasing at the
    same moment would otherwise still be able to arrive out of order.
    """

    def __init__(self, sink: Any) -> None:
        self._sink = sink
        self._lock = threading.Lock()
        self._next = 0
        self._finished: set[int] = set()
        self._waiting: dict[int, list[bytes]] = {}

    def piece(self, idx: int, data: bytes) -> None:
        """One piece of audio for chunk ``idx``."""
        with self._lock:
            self._waiting.setdefault(idx, []).append(data)
            self._release()

    def finish(self, idx: int) -> None:
        """Chunk ``idx`` will produce nothing more."""
        with self._lock:
            self._finished.add(idx)
            self._release()

    def _release(self) -> None:
        """Hand over everything that can be handed over, in order.

        Pieces go through the same buffer as the chunks themselves rather than
        being sent straight when ``idx == _next``: at the moment a chunk becomes
        current, its own earlier pieces may still be sitting in the buffer, and a
        newer piece would overtake them - which sounds like two words swapping
        places.
        """
        while True:
            pieces = self._waiting.get(self._next)
            if pieces:
                for piece in pieces:
                    self._sink(self._next, piece)
                # Cleared rather than removed: if this chunk is not finished yet
                # there are more pieces coming.
                pieces.clear()
            if self._next in self._finished:
                self._waiting.pop(self._next, None)
                self._next += 1
                continue
            break


class _End:
    """Queue marker: the producer is done and every chunk has been handed over."""


def policy_from_dials() -> ChunkPolicy:
    """The chunk thresholds as the settings currently have them.

    Read now rather than captured at import, like every other dial: a host that
    changes one should see it on the next turn, not on the next restart.
    """
    values = dials()
    return ChunkPolicy(
        chunk_chars=values["tts_chunk_chars"],
        chunk_min=values["tts_chunk_min"],
        first_chars=values["tts_first_chars"],
        first_min=values["tts_first_min"],
        first_call_chars=values["tts_first_call_chars"],
        first_call_min=values["tts_first_call_min"],
    )


_pool_lock = threading.Lock()
_pool: ThreadPoolExecutor | None = None


def synthesis_pool() -> ThreadPoolExecutor:
    """The thread pool synthesis runs on, built once for the process.

    Shared rather than one per turn, and bounded rather than unbounded. A pool
    per turn - two workers plus the producer - grows with the number of people
    talking: five hundred simultaneous turns is fifteen hundred threads before
    anything is doing work, and the context switching alone costs everybody their
    first sound. Synthesis is waiting on a network, so a small pool serves a
    large number of turns; the ordering that would otherwise depend on which
    worker ran what is guaranteed by :class:`_AudioOrder`.

    The size is a setting, and it is read when the pool is built rather than per
    turn, because that is when the pool is built.
    """
    global _pool
    with _pool_lock:
        if _pool is None:
            size = max(2, int(dials().get("tts_pool_size") or 32))
            _pool = ThreadPoolExecutor(
                max_workers=size, thread_name_prefix="echoturn-tts"
            )
    return _pool


def shutdown_pool(*, wait: bool = False) -> None:
    """Stop the shared pool, so a process can exit without waiting for it."""
    global _pool
    with _pool_lock:
        pool, _pool = _pool, None
    if pool is not None:
        pool.shutdown(wait=wait)


atexit.register(shutdown_pool)


@dataclass(frozen=True)
class TurnInput:
    """Everything the host knows about the turn it is asking for.

    ``voice_call`` is the caller's answer to "is somebody wearing headphones
    waiting for a reply right now". It only affects how eagerly the first chunk
    is flushed: inside a call a turn is usually one or two sentences, and the
    first sound is very nearly the whole of how fast the reply feels.

    ``history`` is the context window the host is keeping, oldest first. It is
    passed in rather than read from a store because the pipeline has no opinion
    about where a conversation lives - and, more to the point, because a
    transcript that is only ever read cannot be mistaken for the memory of one.
    """

    text: str
    input_kind: str = "text"
    voice_call: bool = False
    system_prompt: str = ""
    history: Sequence[Mapping[str, str]] = ()
    quote: Mapping[str, str] | None = None
    message_id: str = ""


@dataclass
class TurnDeps:
    """What a turn needs in order to run: a model, and optionally a voice.

    ``tts`` being ``None`` is how a host asks for a text-only turn. There is no
    separate flag for it: a flag would be a second way to say the same thing, and
    the two would disagree eventually.
    """

    llm: LLMClient
    tts: TTSClient | None = None
    chunk_policy: ChunkPolicy | None = None
    pool: ThreadPoolExecutor | None = None
    emotion: str | None = None
    voice: str | None = None


class TurnRunner:
    """Runs one turn and yields its events."""

    def __init__(
        self,
        turn: TurnInput,
        deps: TurnDeps,
        *,
        cancel: threading.Event | None = None,
    ) -> None:
        self.turn = turn
        self.deps = deps
        self.cancel = cancel
        self.policy = deps.chunk_policy or policy_from_dials()
        # Resolved on the first submitted chunk rather than here: a text-only
        # turn never synthesises anything, and building a pool it will not use
        # turns every text turn into a thread allocation.
        self.pool = deps.pool
        self.speaking = deps.tts is not None
        self.style = VOICE_STYLE if self.speaking else TEXT_STYLE
        self.queue: queue.Queue = queue.Queue()
        self.stopping = threading.Event()
        self.futures: list[Future] = []
        self.chunk_message: dict[int, int] = {}
        self.raw: list[str] = []
        self.warnings: list[str] = []
        self.failed = False
        self.started = time.monotonic()
        self.first_token_ms: int | None = None
        self.first_audio_ms: int | None = None
        self.order = _AudioOrder(self._emit_audio)

    # ---------------------------------------------------------------- messages

    def messages(self) -> list[dict]:
        """The prompt, assembled the one way this package assembles prompts."""
        out: list[dict] = []
        if str(self.turn.system_prompt or "").strip():
            out.append({"role": "system", "content": str(self.turn.system_prompt)})
        for item in self.turn.history or ():
            out.append(
                {
                    "role": str(item.get("role", "user")),
                    "content": str(item.get("content", "")),
                }
            )
        out.append({"role": "user", "content": self.user_text()})
        return out

    def user_text(self) -> str:
        """This turn's message, with the quoted message in front of it.

        Quoting is our spelling of a convention every chat interface has: the
        quoted message goes in front of the reply to it, marked as a quotation,
        with the model left to work out the rest. Hosts that want a different
        wording should keep the quote out of here and put it in ``history``.
        """
        text = str(self.turn.text or "")
        quote = self.turn.quote or None
        if not quote:
            return text
        quoted = str(quote.get("text", "")).strip()
        if not quoted:
            return text
        who = str(quote.get("role", "them"))
        return f'replying to {who}: "{quoted}"\n{text}'

    # ------------------------------------------------------------------- state

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started) * 1000)

    def stopping_wanted(self) -> bool:
        """Whether anything has asked this turn to stop."""
        return self.stopping.is_set() or (
            self.cancel is not None and self.cancel.is_set()
        )

    # ----------------------------------------------------------- event emitting

    def _emit_audio(self, idx: int, data: bytes) -> None:
        """One ordered piece of audio on its way to the client. Called in a lock."""
        if self.stopping_wanted():
            return
        if self.first_audio_ms is None:
            self.first_audio_ms = self.elapsed_ms()
        self.queue.put(audio(idx, self.chunk_message.get(idx, 0), data))

    # -------------------------------------------------------------- the worker

    def _tap(self, stream: Any) -> Iterator[str]:
        """Pass the model's output through, keeping a copy for the final text.

        The copy is what ``done`` reports. It cannot be reassembled from the
        sentences that were spoken: those are cleaned, cut and re-punctuated, and
        the whole point of reporting the reply is that it says what actually
        arrived.
        """
        for piece in stream:
            if self.first_token_ms is None:
                self.first_token_ms = self.elapsed_ms()
            self.raw.append(piece)
            yield piece

    def _produce(self) -> None:
        """Read the model, cut sentences, accumulate chunks, submit synthesis."""
        idx = 0
        buffer = ""
        current = 0
        try:
            stream = self.deps.llm.stream(self.messages())
            for message_index, line in iter_message_sentences(
                self._tap(stream), style=self.style
            ):
                if self.stopping_wanted():
                    break
                self.queue.put(sentence(message_index, line))
                if not self.speaking:
                    # A text-only turn pays for no synthesis at all, which is
                    # most of what it saves.
                    continue
                if buffer and message_index != current:
                    # A message boundary always ends a chunk. Without this the
                    # audio of two messages would be merged into one chunk and a
                    # client could not tell which bubble it belongs to.
                    self._submit(idx, buffer, current)
                    idx, buffer = idx + 1, ""
                current = message_index
                buffer += line
                if self.policy.should_flush(
                    buffer, first=(idx == 0), call=self.turn.voice_call
                ):
                    self._submit(idx, buffer, current)
                    idx, buffer = idx + 1, ""
            if buffer.strip() and self.speaking and not self.stopping_wanted():
                self._submit(idx, buffer, current)
                idx += 1
        except Exception as exc:  # noqa: BLE001 - the answer is an error event
            log.exception("the reply could not be generated")
            self.queue.put(error(safe_message(exc)))
        finally:
            # ``done`` must not overtake audio, so the chunks are waited for here
            # rather than in the consumer. Except when we are stopping: then
            # nobody is listening and waiting would only delay the exit.
            if not self.stopping_wanted():
                self._wait_for_chunks()
            self.queue.put(_End())

    def _wait_for_chunks(self) -> None:
        """Wait for every submitted chunk, ignoring individual failures.

        A chunk that failed has already recorded a warning and released the
        ordering; there is nothing here to do about it, and raising would turn a
        missing sentence into a missing reply.
        """
        for future in list(self.futures):
            # Reported where it happened; there is nothing to do here about a
            # chunk that already failed.
            with contextlib.suppress(Exception):
                future.result()

    def _submit(self, idx: int, text: str, message: int) -> None:
        """Send one accumulated chunk to synthesis."""
        self.chunk_message[idx] = message
        prepared = prepare_for_tts(text, self.style)
        if self.pool is None:
            self.pool = synthesis_pool()
        self.futures.append(self.pool.submit(self._synthesise, idx, prepared))

    def _synthesise(self, idx: int, text: str) -> None:
        """Synthesise one chunk and hand its audio to the ordering queue.

        Both success and failure end with ``finish``: a chunk that failed must
        still release the ones behind it, or one provider error would silence the
        rest of the reply.
        """
        if self.stopping_wanted():
            self.order.finish(idx)
            return
        try:
            self.deps.tts.synth_stream(
                text,
                emotion=self.deps.emotion,
                voice=self.deps.voice,
                chunk_cb=lambda piece: self.order.piece(idx, piece),
            )
        except Exception as exc:  # noqa: BLE001 - one bad chunk is not a bad turn
            log.warning("chunk %d could not be synthesised: %s", idx, exc)
            self.warnings.append(f"chunk {idx}: {type(exc).__name__}")
        finally:
            self.order.finish(idx)

    # ------------------------------------------------------------- the terminal

    def _finish(self) -> dict:
        """The ``done`` event: the whole reply, and what the turn measured."""
        reply = clean_reply("".join(self.raw), self.style)
        return done(
            reply,
            timings={
                "first_token_ms": self.first_token_ms,
                "first_audio_ms": self.first_audio_ms,
                "total_ms": self.elapsed_ms(),
                "chunks": len(self.chunk_message),
            },
            warnings=self.warnings,
            extra={"input_kind": self.turn.input_kind},
        )

    def _abort(self) -> None:
        """Stop the turn and throw away synthesis that has not started.

        Work already in flight cannot be recalled - the request is out - and
        ``_synthesise`` checks the flag on its way in, so at worst one more chunk
        is paid for and handed to nobody.
        """
        self.stopping.set()
        for future in list(self.futures):
            future.cancel()

    # ------------------------------------------------------------------- public

    def run(self) -> Iterator[dict]:
        """Yield the events of this turn, in order, until it ends."""
        message_id = str(self.turn.message_id or "").strip() or uuid.uuid4().hex
        # ``ack`` goes out before any money is spent and before anything that can
        # be slow: a client uses it to tell "never arrived" from "arrived, and was
        # then interrupted", and without it those two look the same and the user
        # retypes a message that was already received.
        yield ack(message_id)
        # Where the audio is meant to come out. Nothing in this package serves
        # anything but the browser, so this is one event with one value today; it
        # exists so that a host replacing it does not have to change the client.
        yield sink("browser")
        threading.Thread(
            target=self._produce, name="echoturn-reply", daemon=True
        ).start()
        try:
            while True:
                if self.stopping_wanted():
                    self._abort()
                    yield aborted(SUPERSEDED)
                    return
                try:
                    event = self.queue.get(timeout=POLL_SEC)
                except queue.Empty:
                    continue
                if isinstance(event, _End):
                    break
                if event.get("type") == "error":
                    self.failed = True
                yield event
        except GeneratorExit:
            # The consumer is gone - the client disconnected, or a newer request
            # replaced this one. Nothing can be yielded from here: a generator
            # receiving GeneratorExit must not produce another value, which is
            # exactly why this path does not try to send ``aborted``.
            self._abort()
            raise
        if self.failed:
            self._abort()
            return
        yield self._finish()


def run_turn(
    turn: TurnInput,
    deps: TurnDeps,
    *,
    cancel: threading.Event | None = None,
) -> Iterator[dict]:
    """Run one turn of the pipeline and yield its events.

    This is the whole public surface of the core, and it is a generator from the
    first line: nothing is generated, synthesised or paid for until somebody
    starts consuming the events.

    ``cancel`` is the caller's signal that the turn is no longer wanted. It is
    checked between events, so it is felt within :data:`POLL_SEC`; closing the
    generator works as well and is what a disconnected client causes.
    """
    return TurnRunner(turn, deps, cancel=cancel).run()
