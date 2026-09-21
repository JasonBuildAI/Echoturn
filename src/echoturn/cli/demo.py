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
import threading
from collections.abc import Callable, Mapping

from ..audio import decode_16k_mono, pcm16_to_wav, read_wav
from ..config import dials, env_str
from ..pipeline import TurnDeps, TurnInput, run_turn
from ..providers import make_asr, make_llm, make_tts
from ..store import InMemoryStore, TranscriptStore
from ..vad import build_vad
from .audio import Listener, Speaker

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


class Ear:
    """A microphone and a recogniser, and the one gate between them.

    A recording with no speech in it is not a turn. It is a cough, a door, or the
    sound of somebody deciding not to say anything - and sending it on costs a
    recognition, a reply, and a bill for both. The measurement is the package's
    own, and its answer says whether the speech model ran or a level threshold
    stood in for it, so a machine that was supposed to have the model can find
    out that it does not.
    """

    def __init__(
        self,
        *,
        listener,
        asr,
        echo: Callable[[str], None] = print,
        min_speech_ms: int | None = None,
        vad=None,
    ) -> None:
        self.listener = listener
        self.asr = asr
        self.echo = echo
        self._min_speech_ms = min_speech_ms
        self._vad = vad
        self.reported = ""

    def min_speech_ms(self) -> int:
        """How much speech a recording needs, from the table like everything else."""
        if self._min_speech_ms is not None:
            return int(self._min_speech_ms)
        return int(dials()["min_speech_ms"])

    def detector(self):
        """The speech detector, built once and then reused."""
        if self._vad is None:
            self._vad = build_vad()
        return self._vad

    def hear(self, stop) -> str:
        """Record one turn and return what was said; empty when it is not a turn."""
        pcm = self.listener.record(stop)
        if not pcm:
            self.echo(self.listener.error or "nothing was recorded")
            return ""
        wav = pcm16_to_wav(pcm, self.listener.rate)
        speech = self.detector().report(decode_16k_mono(wav)).get("speech_ms")
        if not self._is_speech(speech):
            self.echo("that was too short to be a turn")
            return ""
        return self.asr.transcribe(
            wav,
            sample_rate=self.listener.rate,
            fmt="wav",
            lang=str(dials()["lang"]),
        )

    def _is_speech(self, speech) -> bool:
        """Whether a recording is worth sending.

        Unknown is not "no". When nothing could measure the speech - no numeric
        stack, no model, a detector that failed - the recording is sent anyway:
        dropping a real sentence on the strength of a measurement that never
        happened is the worse of the two mistakes, and the fallback is said out
        loud so that it is not mistaken for the model agreeing.
        """
        if speech is None:
            self._report_fallback()
            return True
        return int(speech) >= self.min_speech_ms()

    def _report_fallback(self) -> None:
        """Say once why nothing measured the speech."""
        reason = getattr(self.detector(), "reason", "")
        if reason and reason != self.reported:
            self.reported = str(reason)
            self.echo(f"note: {reason}")


class Once:
    """Something worth saying the first time and not the twentieth.

    A machine with no sound card is not a different problem on the second reply,
    and repeating the same line under every turn buries the reply it is about.
    """

    def __init__(self, echo: Callable[[str], None] = print) -> None:
        self.echo = echo
        self.said: set[str] = set()

    def say(self, text: str) -> bool:
        """Say ``text`` if it has not been said; true when it was."""
        if not text or text in self.said:
            return False
        self.said.add(str(text))
        self.echo(str(text))
        return True


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
    parser.add_argument(
        "--mic",
        action="store_true",
        help="talk instead of typing: enter to start, enter again to send",
    )
    parser.add_argument(
        "--no-play",
        action="store_true",
        help="print the reply without sending its audio to a speaker",
    )
    return parser.parse_args(argv)


def _stop_on_enter(source, stop) -> None:
    """Read one line from the keyboard, then signal the recording to stop."""
    source.readline()
    stop.set()


def conversation(
    session,
    *,
    ear,
    speaker=None,
    play: bool = True,
    source=None,
    echo: Callable[[str], None] = print,
) -> int:
    """One turn per pair of enter presses, until the input ends.

    Enter starts the recording and enter sends it. The terminal has no other way
    to say "I have finished": a keyboard has no release, and guessing from the
    silence would be a second endpointing rule living in a demo - a worse one,
    on the one surface where nobody would ever look for it.
    """
    source = sys.stdin if source is None else source
    if speaker is None:
        speaker = Speaker()
    device_problem = Once(lambda line: print(line, file=sys.stderr, flush=True))
    while True:
        if source.readline() == "":
            return 0
        stop = threading.Event()
        # The keyboard is read on a thread of its own because this one is about
        # to block on the sound card, and a blocking read that cannot be
        # interrupted is what makes the second thread necessary.
        threading.Thread(
            target=_stop_on_enter, args=(source, stop), daemon=True
        ).start()
        echo("listening - press enter to send")
        text = ear.hear(stop)
        if not text:
            continue
        said = session.say(text, input_kind="voice")
        if (
            play
            and said["audio"]
            and not speaker.play(said["audio"], said["sample_rate"])
        ):
            device_problem.say(speaker.error)


def main(
    argv: list[str] | None = None, *, session=None, speaker=None, ear=None
) -> int:
    """Read a turn from the terminal, print it, repeat until end of input.

    The session, the speaker and the ear are injectable so that the loops can be
    tested without a sound card and without a provider: what is worth checking
    here is the loop, not the wiring it was handed.
    """
    args = parse_args(argv)
    if session is None:
        session = Session(
            llm=make_llm(),
            tts=make_tts(),
            system_prompt=args.system,
            echo=lambda line: print(f"assistant> {line}", flush=True),
        )
    if speaker is None:
        speaker = Speaker()
    if args.mic:
        if ear is None:
            ear = Ear(listener=Listener(), asr=make_asr())
        return conversation(
            session, ear=ear, speaker=speaker, play=not args.no_play
        )
    device_problem = Once(lambda line: print(line, file=sys.stderr, flush=True))
    for line in sys.stdin:
        if not line.strip():
            continue
        said = session.say(line)
        if args.no_play or not said["audio"]:
            continue
        if not speaker.play(said["audio"], said["sample_rate"]):
            device_problem.say(speaker.error)
    return 0


if __name__ == "__main__":  # pragma: no cover - the entry point itself
    raise SystemExit(main())
