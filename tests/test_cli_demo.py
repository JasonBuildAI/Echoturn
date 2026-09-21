"""The terminal demo: what a host has to add, and what it must not lose."""
from __future__ import annotations

import base64

from echoturn.audio import pcm16_to_wav
from echoturn.cli.demo import ClipCollector, Session, parse_args
from echoturn.store import InMemoryStore
from pipeline_helpers import FakeLLM, FakeTTS

REPLY = "First sentence, long enough not to be joined. Second one, also long enough."


def collector() -> ClipCollector:
    return ClipCollector()


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
