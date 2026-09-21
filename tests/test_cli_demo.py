"""The terminal demo: what a host has to add, and what it must not lose."""
from __future__ import annotations

import base64
import io

from echoturn.audio import pcm16_to_wav
from echoturn.cli.audio import Speaker
from echoturn.cli.demo import ClipCollector, Ear, Once, Session, main, parse_args
from echoturn.providers import MockTTS
from echoturn.store import InMemoryStore
from pipeline_helpers import FakeASR, FakeLLM, FakeTTS

REPLY = "First sentence, long enough not to be joined. Second one, also long enough."


def collector() -> ClipCollector:
    return ClipCollector()


def real_voice() -> MockTTS:
    """A voice whose output is a real container.

    The scripted voice in `pipeline_helpers` writes four bytes that only look
    like a header, which is right for the pipeline - nothing in it reads the
    audio - and wrong here: this demo parses the container, and a test written
    against stand-in bytes would be asserting about an empty reply.
    """
    return MockTTS()


class DeafSpeaker(Speaker):
    """A speaker that records the attempts and always refuses."""

    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0
        self.error = "no audio device: pip install 'echoturn[cli]'"

    def play(self, pcm: bytes, sample_rate: int) -> bool:
        self.attempts += 1
        return False


def run_cli(monkeypatch, lines: list[str], **kwargs):
    """Run the command line over a scripted stdin, and capture both streams."""
    monkeypatch.setattr("sys.stdin", io.StringIO("\n".join(lines) + "\n"))
    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    monkeypatch.setattr("sys.stderr", err)
    code = main([], **kwargs)
    return code, out.getvalue(), err.getvalue()


def clip(marker: bytes, samples: int = 8) -> str:
    wav = pcm16_to_wav(marker * (samples * 2), 16000)
    return base64.b64encode(wav).decode()


def test_audio_is_taken_in_the_order_it_was_written():
    """Synthesis finishes out of order; playback must not follow it."""
    taken = collector()
    assert taken.add(1, base64.b64decode(clip(b"\x01"))) == 0
    assert taken.pcm == b""
    assert taken.chunks == 0
    assert taken.add(0, base64.b64decode(clip(b"\x00"))) == 2
    assert taken.chunks == 2
    assert taken.sample_rate == 16000
    assert taken.pcm == b"\x00" * 16 + b"\x01" * 16


def test_a_chunk_that_cannot_be_read_still_counts_as_one():
    """A count that skipped it would make the audio look complete."""
    taken = collector()
    taken.add(0, b"not a wav at all")
    assert taken.chunks == 1
    assert taken.pcm == b""


def test_a_turn_is_reported_as_it_reaches_the_voice():
    lines: list[str] = []
    session = Session(llm=FakeLLM([REPLY]), tts=FakeTTS(), echo=lines.append)
    out = session.say("hello")
    assert out["reply"] == REPLY
    assert out["chunks"] > 0
    # What is reported is the text of each synthesis request, in order - not the
    # sentences of the reply. They are different things, and joining the first to
    # get the second is a piece of arithmetic that does not hold.
    assert lines == [
        "First sentence, long enough not to be joined. Second one,",
        "also long enough.",
    ]


def test_a_text_only_turn_produces_no_audio():
    session = Session(llm=FakeLLM([REPLY]), tts=FakeTTS(), echo=lambda _: None)
    out = session.say("hello", speak=False)
    assert out["chunks"] == 0
    assert out["audio"] == b""


def test_the_window_carries_the_turn_before_this_one():
    llm = FakeLLM([REPLY])
    session = Session(llm=llm, tts=None, echo=lambda _: None)
    session.say("first thing")
    session.say("second thing")
    assert [message["role"] for message in llm.prompts[1]] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert llm.prompts[1][3]["content"] == "second thing"


def test_an_empty_line_never_reaches_the_model():
    llm = FakeLLM([REPLY])
    session = Session(llm=llm, echo=lambda _: None)
    session.say("   ")
    assert llm.calls == 0


def test_the_system_line_can_be_replaced_from_the_command_line():
    args = parse_args(["--system", "Be terse."])
    assert args.system == "Be terse."
    session = Session(
        llm=FakeLLM([REPLY]), system_prompt=args.system, echo=lambda _: None
    )
    assert session.say("hello")["reply"] == REPLY


def test_the_demo_keeps_its_conversation_in_a_store_it_was_given():
    store = InMemoryStore()
    session = Session(llm=FakeLLM([REPLY]), store=store, echo=lambda _: None)
    session.say("are you there")
    assert [message["role"] for message in store.window("terminal")] == [
        "user",
        "assistant",
    ]


def test_the_reply_is_played_after_the_turn_that_produced_it(monkeypatch):
    session = Session(llm=FakeLLM([REPLY]), tts=real_voice(), echo=lambda _: None)
    speaker = DeafSpeaker()
    code, _, err = run_cli(monkeypatch, ["hello"], session=session, speaker=speaker)
    assert code == 0
    assert speaker.attempts == 1
    # Said once, in the stream meant for it: a missing sound card is not a
    # different problem on the second reply.
    assert err.count("no audio device") == 1
    _, _, again = run_cli(
        monkeypatch, ["one", "two"], session=session, speaker=DeafSpeaker()
    )
    assert again.count("no audio device") == 1


def test_a_turn_that_produced_no_audio_is_not_sent_to_the_speaker(monkeypatch):
    session = Session(llm=FakeLLM([REPLY]), tts=None, echo=lambda _: None)
    speaker = DeafSpeaker()
    run_cli(monkeypatch, ["hello"], session=session, speaker=speaker)
    assert speaker.attempts == 0


def test_an_empty_line_does_not_start_a_turn_on_the_command_line(monkeypatch):
    session = Session(llm=FakeLLM([REPLY]), tts=real_voice(), echo=lambda _: None)
    speaker = DeafSpeaker()
    code, _, _ = run_cli(
        monkeypatch, ["", "   ", "real"], session=session, speaker=speaker
    )
    assert code == 0
    assert speaker.attempts == 1


class ScriptedMicrophone:
    """A microphone that answers with the audio it was told to."""

    def __init__(self, pcm: bytes = b"", *, rate: int = 16000, error: str = "") -> None:
        self.pcm = pcm
        self.rate = rate
        self.error = error
        self.stops: list[object] = []

    def record(self, stop) -> bytes:
        self.stops.append(stop)
        return self.pcm


class ScriptedDetector:
    """A speech detector that answers with what it was told to."""

    def __init__(self, report: dict | None = None, reason: str = "") -> None:
        self.answer = dict(report or {})
        self.reason = reason
        self.samples: list[object] = []

    def report(self, samples) -> dict:
        self.samples.append(samples)
        return dict(self.answer)


SECOND = pcm16_to_wav(b"\x00\x00" * 16000, 16000)


def ear(**kwargs):
    said: list[str] = []
    asr = FakeASR("what was said")
    heard = Ear(asr=asr, echo=said.append, min_speech_ms=300, **kwargs)
    return heard, asr, said


def test_a_recording_with_speech_in_it_is_recognised():
    listener = ScriptedMicrophone(b"\x00\x00" * 16000)
    heard, asr, _ = ear(listener=listener, vad=ScriptedDetector({"speech_ms": 900}))
    assert heard.hear(object()) == "what was said"
    assert asr.calls == [
        {"bytes": len(SECOND), "sample_rate": 16000, "fmt": "wav", "lang": "auto"}
    ]


def test_a_recording_with_too_little_speech_never_reaches_the_recogniser():
    """A cough is not a turn, and sending it costs a reply and a bill for one."""
    heard, asr, said = ear(
        listener=ScriptedMicrophone(b"\x00\x00" * 16000),
        vad=ScriptedDetector({"speech_ms": 80}),
    )
    assert heard.hear(object()) == ""
    assert asr.calls == []
    assert said == ["that was too short to be a turn"]


def test_a_recording_nothing_could_measure_is_sent_anyway():
    """Dropping a real sentence on a measurement that never happened is worse."""
    heard, asr, said = ear(
        listener=ScriptedMicrophone(b"\x00\x00" * 16000),
        vad=ScriptedDetector({}, reason="the speech model is not there"),
    )
    assert heard.hear(object()) == "what was said"
    assert len(asr.calls) == 1
    assert said == ["note: the speech model is not there"]
    # Said once: a machine without the model is not a new problem every turn.
    heard.hear(object())
    assert said == ["note: the speech model is not there"]


def test_a_recording_of_nothing_says_why_it_was_empty():
    heard, _, said = ear(
        listener=ScriptedMicrophone(b"", error="device busy"),
        vad=ScriptedDetector({"speech_ms": 900}),
    )
    assert heard.hear(object()) == ""
    assert said == ["device busy"]


def test_the_gate_reads_the_dial_table_when_no_number_is_given():
    from echoturn.config import dials

    heard = Ear(listener=ScriptedMicrophone(), asr=FakeASR())
    assert heard.min_speech_ms() == dials()["min_speech_ms"]


def test_a_message_worth_saying_once_is_said_once():
    said: list[str] = []
    once = Once(said.append)
    assert once.say("no audio device") is True
    assert once.say("no audio device") is False
    assert once.say("") is False
    assert once.say("something else") is True
    assert said == ["no audio device", "something else"]
