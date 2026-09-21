"""A conversation in a terminal.

This is the second reference assembly in the repository, and it exists for the
opposite reason to ``examples/minimal_call``: the web example shows what a host
has to *add* to put a conversation in a browser, and this one shows how little a
host has to add to put one anywhere. One loop, one provider set, one window - and
every decision worth arguing about lives in the package it imports.

    python -m echoturn.cli.demo

Typed input and spoken input reach the same place. They differ in how the text
arrived, not in what happens to it afterwards, which is why nothing below asks
which kind of turn it is running except to label it.
"""
from __future__ import annotations

import argparse
import base64
import sys
from collections.abc import Callable, Mapping

from ..audio import read_wav
from ..config import env_str
from ..pipeline import TurnDeps, TurnInput, run_turn
from ..providers import make_llm, make_tts
from ..store import InMemoryStore, TranscriptStore

# The one thing a demo has to decide for itself. A host would put its own
# product's prompt here; a pipeline cannot guess one, and a default that
# pretended to be a personality would be worse than a plain instruction.
DEFAULT_SYSTEM_PROMPT = env_str(
    "ECHOTURN_DEMO_SYSTEM",
    "You are a helpful voice assistant. Answer in one or two short sentences.",
)


class ClipCollector:
    """The reply's audio, in the order it was written.

    Synthesis finishes out of order by nature - the second chunk of a reply is
    often ready before the first - so a consumer that played chunks as they
    arrived would say the reply's sentences in the order the voice service
    happened to finish them. The index is what makes that impossible, and holding
    a chunk until its turn is the whole job here.

    A chunk whose container cannot be read still counts as a chunk: it was
    produced, it was paid for, and a count that quietly skipped it would make the
    assembled audio look complete when it is missing a piece.
    """

    def __init__(self) -> None:
        self._pending: dict[int, bytes] = {}
        self.expected = 0
        self.pcm = b""
        self.sample_rate = 0

    @property
    def chunks(self) -> int:
        """How many chunks have been taken in order so far."""
        return self.expected

    def add(self, index: int, data: bytes) -> int:
        """Take one chunk; return how many were flushed by taking it."""
        self._pending[int(index)] = bytes(data or b"")
        flushed = 0
        while self.expected in self._pending:
            info = read_wav(self._pending.pop(self.expected))
            self.expected += 1
            flushed += 1
            if info is not None:
                self.pcm += info.pcm
                self.sample_rate = info.sample_rate or self.sample_rate
        return flushed


class Session:
    """One conversation, from the terminal's point of view.

    The window it keeps is handed to the model and nothing else. There is no
    memory here and there is not meant to be: a host that wants the assistant to
    remember last week brings a system for that, and this class would go on
    working exactly as it does.
    """

    def __init__(
        self,
        *,
        llm,
        tts=None,
        store: TranscriptStore | None = None,
        key: str = "terminal",
        system_prompt: str = "",
        voice: str | None = None,
        emotion: str | None = None,
        echo: Callable[[str], None] = print,
    ) -> None:
        self.llm = llm
        self.tts = tts
        self.store = store if store is not None else InMemoryStore()
        self.key = key
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.voice = voice
        self.emotion = emotion
        self.echo = echo

    def say(self, text: str, *, input_kind: str = "text", speak: bool = True) -> dict:
        """Run one turn, reporting it as it happens.

        Returns what the turn produced rather than only printing it, because the
        caller is what knows whether the audio is going to a speaker, a file or
        nowhere - and this class should not have to.
        """
        message = str(text or "").strip()
        if not message:
            return {"reply": "", "audio": b"", "sample_rate": 0, "chunks": 0}
        self.store.append(self.key, "user", message)
        clip = ClipCollector()
        reply = ""
        for event in run_turn(
            TurnInput(
                text=message,
                input_kind=input_kind,
                system_prompt=self.system_prompt,
                history=self.store.window(self.key)[:-1],
            ),
            TurnDeps(
                llm=self.llm,
                tts=self.tts if speak else None,
                voice=self.voice,
                emotion=self.emotion,
            ),
        ):
            reply = self._report(event, clip, reply)
        self.store.append(self.key, "assistant", reply)
        return {
            "reply": reply,
            "audio": clip.pcm,
            "sample_rate": clip.sample_rate,
            "chunks": clip.chunks,
        }

    def _report(self, event: Mapping, clip: ClipCollector, reply: str) -> str:
        """Print one event, and say what the reply now stands at."""
        kind = event.get("type")
        if kind == "sentence":
            self.echo(str(event.get("text", "")))
        elif kind == "audio":
            clip.add(int(event.get("idx", 0)), _decode(event.get("data", "")))
        elif kind == "done":
            reply = str(event.get("reply", ""))
        elif kind == "error":
            self.echo(f"failed: {event.get('error', '')}")
        elif kind == "aborted":
            self.echo(f"stopped: {event.get('reason', '')}")
        return reply


def _decode(data: object) -> bytes:
    """One event's payload as bytes; unreadable payloads become nothing."""
    try:
        return base64.b64decode(str(data or ""), validate=True)
    except Exception:  # noqa: BLE001 - a broken frame is one lost chunk
        return b""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """The flags, and the only place their defaults are written."""
    parser = argparse.ArgumentParser(
        prog="python -m echoturn.cli.demo",
        description="Talk to the pipeline from a terminal.",
    )
    parser.add_argument(
        "--system",
        default="",
        help="what the assistant is told it is; overrides the built-in line",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Read a turn from the terminal, print it, repeat until end of input."""
    args = parse_args(argv)
    session = Session(
        llm=make_llm(),
        tts=make_tts(),
        system_prompt=args.system,
        echo=lambda line: print(f"assistant> {line}", flush=True),
    )
    for line in sys.stdin:
        if line.strip():
            session.say(line)
    return 0


if __name__ == "__main__":  # pragma: no cover - the entry point itself
    raise SystemExit(main())
