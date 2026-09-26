import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from echoturn.errors import ProviderError
from echoturn.pipeline import TurnDeps, TurnInput, policy_from_dials, run_turn
from pipeline_helpers import (
    AbandonedTTS,
    BrokenLLM,
    FakeLLM,
    FakeTTS,
    HalfSpeakingTTS,
    SilentTTS,
)

# One sentence each, and long enough that the shipped thresholds send each of
# them as a chunk of its own: a test should not depend on where the chunker
# happens to cut.
SENTENCE_A = "第一句话要写得足够长才不会被并进上一片。"
SENTENCE_B = "第二句话也要足够长才能单独成一片送出去。"


class SlowLLM:
    """One sentence immediately, then nothing for a long time."""

    def __init__(self, first: str, then_delay: float) -> None:
        self.first = first
        self.then_delay = then_delay

    def stream(self, messages):
        yield self.first
        time.sleep(self.then_delay)
        yield SENTENCE_B


@pytest.fixture
def pool():
    executor = ThreadPoolExecutor(max_workers=4)
    yield executor
    executor.shutdown(wait=False)


def collect(turn, deps, cancel=None, pool=None):
    deps = TurnDeps(**{**deps.__dict__, "pool": pool or deps.pool})
    return list(run_turn(turn, deps, cancel=cancel))


def deps_for(llm, tts, pool):
    return TurnDeps(llm=llm, tts=tts, pool=pool, chunk_policy=policy_from_dials())


def audio_indices(events):
    return [event["idx"] for event in events if event["type"] == "audio"]


def types(events):
    return [event["type"] for event in events]


def test_a_turn_opens_with_ack_and_sink_and_ends_with_done(pool):
    llm = FakeLLM([SENTENCE_A])
    events = collect(
        TurnInput("hello"), deps_for(llm, FakeTTS(), pool), pool=pool
    )
    assert types(events)[0] == "ack"
    assert types(events)[1] == "sink"
    assert events[-1]["type"] == "done"
    assert "done" not in types(events)[:-1]


def test_the_ack_carries_the_id_the_host_supplied(pool):
    events = collect(
        TurnInput("hello", message_id="m-7"),
        deps_for(FakeLLM([SENTENCE_A]), None, pool),
        pool=pool,
    )
    assert events[0] == {"type": "ack", "id": "m-7"}


def test_the_ack_gets_an_id_when_the_host_has_none(pool):
    events = collect(
        TurnInput("hello"), deps_for(FakeLLM([SENTENCE_A]), None, pool), pool=pool
    )
    assert len(events[0]["id"]) == 32
    assert events[0]["id"].isalnum()


def test_sentences_arrive_before_the_audio_that_says_them(pool):
    events = collect(
        TurnInput("hello"),
        deps_for(FakeLLM([SENTENCE_A, SENTENCE_B]), FakeTTS(), pool),
        pool=pool,
    )
    order = types(events)
    assert order.index("sentence") < order.index("audio")


def test_audio_is_numbered_from_zero_without_gaps(pool):
    events = collect(
        TurnInput("hello"),
        deps_for(FakeLLM([SENTENCE_A, SENTENCE_B]), FakeTTS(), pool),
        pool=pool,
    )
    assert audio_indices(events) == [0, 1]


def test_a_chunk_that_finishes_first_still_plays_second(pool):
    """The ordering is the contract, not the arrival time of the audio."""
    tts = FakeTTS(delays=[0.25, 0.0])
    events = collect(
        TurnInput("hello"),
        deps_for(FakeLLM([SENTENCE_A, SENTENCE_B]), tts, pool),
        pool=pool,
    )
    assert audio_indices(events) == [0, 1]
    assert tts.completed == [1, 0]


def test_the_done_event_reports_the_whole_reply_and_what_it_measured(pool):
    events = collect(
        TurnInput("hello"),
        deps_for(FakeLLM([SENTENCE_A, SENTENCE_B]), FakeTTS(), pool),
        pool=pool,
    )
    final = events[-1]
    assert final["reply"] == SENTENCE_A + SENTENCE_B
    assert final["timings"]["chunks"] == 2
    assert isinstance(final["timings"]["first_token_ms"], int)
    assert isinstance(final["timings"]["first_audio_ms"], int)
    assert final["timings"]["total_ms"] >= final["timings"]["first_audio_ms"]
    assert final["warnings"] == []
    assert final["extra"] == {"input_kind": "text"}


def test_the_first_sound_is_measured_before_the_last_chunk_finishes(pool):
    """first_audio_ms is when sound started, not when the reply was done."""
    tts = FakeTTS(delays=[0.0, 0.3])
    events = collect(
        TurnInput("hello"),
        deps_for(FakeLLM([SENTENCE_A, SENTENCE_B]), tts, pool),
        pool=pool,
    )
    timings = events[-1]["timings"]
    assert timings["first_audio_ms"] < timings["total_ms"]


def test_audio_belongs_to_the_message_it_was_written_in(pool):
    llm = FakeLLM([SENTENCE_A + "\n\n" + SENTENCE_B])
    events = collect(
        TurnInput("hello"), deps_for(llm, FakeTTS(), pool), pool=pool
    )
    audio = [event for event in events if event["type"] == "audio"]
    assert [event["i"] for event in audio] == [0, 1]


def test_the_whole_reply_is_cut_at_message_boundaries(pool):
    llm = FakeLLM([SENTENCE_A + "\n\n" + SENTENCE_B])
    events = collect(
        TurnInput("hello"), deps_for(llm, FakeTTS(), pool), pool=pool
    )
    assert events[-1]["reply"] == SENTENCE_A + "\n\n" + SENTENCE_B


def test_a_text_only_turn_synthesises_nothing(pool):
    events = collect(
        TurnInput("hello"), deps_for(FakeLLM([SENTENCE_A]), None, pool), pool=pool
    )
    assert audio_indices(events) == []
    assert events[-1]["type"] == "done"
    assert events[-1]["reply"] == SENTENCE_A


def test_the_reply_is_cleaned_before_it_is_reported(pool):
    llm = FakeLLM(["She said </think>only this in the end."])
    events = collect(
        TurnInput("hello"), deps_for(llm, None, pool), pool=pool
    )
    assert events[-1]["reply"] == "only this in the end."


def test_a_failing_model_ends_the_turn_with_one_readable_error(pool):
    events = collect(
        TurnInput("hello"),
        deps_for(BrokenLLM(ProviderError("the model is unavailable")), None, pool),
        pool=pool,
    )
    assert events[-1] == {
        "type": "error",
        "error": "the model is unavailable",
    }
    assert "done" not in types(events)


def test_an_unexpected_failure_does_not_leak_its_text(pool):
    events = collect(
        TurnInput("hello"),
        deps_for(BrokenLLM(RuntimeError("/srv/internal/path failed")), None, pool),
        pool=pool,
    )
    assert events[-1]["type"] == "error"
    assert "/srv/internal" not in events[-1]["error"]


def test_one_chunk_that_fails_to_speak_does_not_silence_the_rest(pool):
    """A failure that does not repeat: the chunk is sent again and is heard."""
    tts = FakeTTS(fail_on=[0])
    events = collect(
        TurnInput("hello"),
        deps_for(FakeLLM([SENTENCE_A, SENTENCE_B]), tts, pool),
        pool=pool,
    )
    final = events[-1]
    assert final["type"] == "done"
    assert audio_indices(events) == [0, 1]
    assert final["warnings"] == []
    assert final["unspoken"] == []
    assert final["reply"] == SENTENCE_A + SENTENCE_B
    # Two chunks, one of them sent twice: the retry is bounded to one attempt.
    assert tts.streamed == 3


def test_a_chunk_that_never_speaks_is_reported_without_taking_the_turn_down(pool):
    tts = FakeTTS(fail_all=True)
    events = collect(
        TurnInput("hello"),
        deps_for(FakeLLM([SENTENCE_A, SENTENCE_B]), tts, pool),
        pool=pool,
    )
    final = events[-1]
    assert final["type"] == "done"
    assert audio_indices(events) == []
    assert final["warnings"] == ["chunk 0: RuntimeError", "chunk 1: RuntimeError"]
    assert final["unspoken"] == [0], "the whole message has no sound"
    assert final["reply"] == SENTENCE_A + SENTENCE_B, "the text is still there to read"
    assert tts.streamed == 4, "each chunk is tried exactly twice"


def test_only_the_message_with_no_sound_is_named(pool):
    """Two messages: the first never speaks, the second does.

    The list is per message rather than per chunk on purpose - it answers "which
    bubble can this person not play" - and a message with some of its audio is a
    bubble that plays.

    The failure is named by text rather than by call: the retry for one chunk
    runs alongside the other chunk's first attempt, so "the third call failed"
    says nothing about which message went silent.
    """
    tts = FakeTTS(fail_containing="第一句话")
    events = collect(
        TurnInput("hello"),
        deps_for(FakeLLM([SENTENCE_A + "\n\n" + SENTENCE_B]), tts, pool),
        pool=pool,
    )
    final = events[-1]
    assert final["type"] == "done"
    assert audio_indices(events) == [1]
    assert final["warnings"] == ["chunk 0: RuntimeError"]
    assert final["unspoken"] == [0]
    assert SENTENCE_A in final["reply"] and SENTENCE_B in final["reply"]


def test_a_chunk_that_broke_after_some_audio_is_not_said_twice(pool):
    """Half a sentence is already out; re-synthesising it would repeat it."""
    tts = HalfSpeakingTTS()
    events = collect(
        TurnInput("hello"),
        deps_for(FakeLLM([SENTENCE_A]), tts, pool),
        pool=pool,
    )
    final = events[-1]
    assert final["type"] == "done"
    assert tts.calls == 1, "no retry once something has been heard"
    assert audio_indices(events) == [0]
    assert final["warnings"] == ["chunk 0: RuntimeError"]
    assert final["unspoken"] == [], "the message did make a sound"


def test_a_turn_that_was_given_up_on_does_not_pay_for_a_second_attempt(pool):
    """The retry is for a listener who is still there."""
    cancel = threading.Event()
    tts = AbandonedTTS(cancel)
    events = collect(
        TurnInput("hello"),
        deps_for(FakeLLM([SENTENCE_A, SENTENCE_B]), tts, pool),
        cancel=cancel,
        pool=pool,
    )
    assert tts.calls == 1, "a chunk that failed after the client left is not retried"
    assert audio_indices(events) == []
    # Whether the cancel is noticed before or after the last event is a race
    # between the worker and the poll; either ending is this turn, and neither
    # of them paid for a second attempt.
    assert events[-1]["type"] in ("aborted", "done")


def test_a_text_turn_never_names_a_silent_message(pool):
    """A turn with no voice was never meant to make a sound."""
    events = collect(
        TurnInput("hello"),
        deps_for(FakeLLM([SENTENCE_A, SENTENCE_B]), None, pool),
        pool=pool,
    )
    final = events[-1]
    assert final["unspoken"] == []
    assert final["warnings"] == []
    assert audio_indices(events) == []


def test_the_turn_reports_what_the_caller_measured_before_it_arrived(pool):
    """The recogniser runs on the caller's clock; only the caller can time it.

    Without this the turn reports the part of the wait that happens on this side
    of the request and nothing about the part a person actually notices: the
    recogniser thinking after they stopped talking.
    """
    events = collect(
        TurnInput("hello", client_timings={"asr_verdict_ms": 620}),
        deps_for(FakeLLM([SENTENCE_A]), FakeTTS(), pool),
        pool=pool,
    )
    timings = events[-1]["timings"]
    assert timings["asr_verdict_ms"] == 620
    assert timings["asr_to_first_token_ms"] == timings["first_token_ms"]
    assert timings["total_first_audio_ms"] == 620 + timings["first_audio_ms"]
    assert timings["first_token_to_first_audio_ms"] == (
        timings["first_audio_ms"] - timings["first_token_ms"]
    )


def test_a_measurement_that_is_not_a_number_is_dropped_rather_than_guessed(pool):
    """Timings are read as facts, so a truthy string is not a measurement."""
    events = collect(
        TurnInput(
            "hello",
            client_timings={"asr_verdict_ms": "620", "also": True},
        ),
        deps_for(FakeLLM([SENTENCE_A]), FakeTTS(), pool),
        pool=pool,
    )
    timings = events[-1]["timings"]
    assert timings["asr_verdict_ms"] is None
    assert timings["asr_to_first_token_ms"] is None
    assert timings["total_first_audio_ms"] is None


def test_a_text_turn_reports_no_part_of_a_wait_it_never_had(pool):
    """Every derived gap is null, and the plain measurements are what they are."""
    events = collect(
        TurnInput("hello"),
        deps_for(FakeLLM([SENTENCE_A]), None, pool),
        pool=pool,
    )
    timings = events[-1]["timings"]
    assert timings["asr_verdict_ms"] is None
    assert timings["total_first_audio_ms"] is None
    assert timings["first_audio_ms"] is None
    assert timings["first_token_to_first_audio_ms"] is None
    assert timings["total_ms"] >= 0


def test_a_negative_measurement_is_refused(pool):
    """A gap that runs backwards is a broken clock, not a fast answer."""
    events = collect(
        TurnInput("hello", client_timings={"asr_verdict_ms": -5}),
        deps_for(FakeLLM([SENTENCE_A]), FakeTTS(), pool),
        pool=pool,
    )
    assert events[-1]["timings"]["asr_verdict_ms"] is None


def test_a_provider_that_returns_no_audio_is_not_a_failure(pool):
    events = collect(
        TurnInput("hello"),
        deps_for(FakeLLM([SENTENCE_A]), SilentTTS(), pool),
        pool=pool,
    )
    assert audio_indices(events) == []
    assert events[-1]["type"] == "done"
    assert events[-1]["warnings"] == []


def test_cancelling_ends_the_turn_with_aborted_and_no_done(pool):
    cancel = threading.Event()
    llm = FakeLLM([SENTENCE_A, SENTENCE_B, SENTENCE_A], delay=0.01)
    events = []
    for event in run_turn(
        TurnInput("hello"), deps_for(llm, FakeTTS(), pool), cancel=cancel
    ):
        if event["type"] == "sentence":
            cancel.set()
        events.append(event)
    assert events[-1]["type"] == "aborted"
    assert events[-1]["reason"] == "superseded"
    assert "done" not in types(events)


def test_a_cancelled_turn_exits_within_one_poll_interval(pool):
    """The producer is silent here, so only the poll can save us."""
    cancel = threading.Event()
    deps = deps_for(SlowLLM("四字句。", 5.0), None, pool)
    started = None
    events = []
    for event in run_turn(TurnInput("hello"), deps, cancel=cancel):
        events.append(event)
        if event["type"] == "sentence" and started is None:
            cancel.set()
            started = time.monotonic()
    assert events[-1]["type"] == "aborted"
    assert started is not None
    assert time.monotonic() - started < 0.4


def test_closing_the_generator_abandons_the_rest_of_the_work(pool):
    # One sentence every 300 ms, so the pipeline cannot have submitted the whole
    # reply by the time the first chunk is ready. With an instant model all eight
    # chunks are submitted at once, and then whether the pool got to the queued
    # ones before the abort is a race with the machine - which is how this test
    # came to fail on a busy laptop and pass on an idle one.
    tts = FakeTTS(delays=[0.2] * 12)
    llm = FakeLLM([SENTENCE_A] * 12, delay=0.3)
    turn = TurnInput("hello")
    gen = run_turn(turn, deps_for(llm, tts, pool))
    for event in gen:
        if event["type"] == "audio":
            break
    gen.close()
    time.sleep(0.4)
    settled = tts.streamed
    time.sleep(0.8)
    assert tts.streamed == settled, "synthesis started after the caller left"
    assert settled < 12, "the whole reply was synthesised after the caller left"


def test_a_voice_call_flushes_the_first_chunk_earlier(pool):
    """Inside a call the first sound is nearly all of the perceived speed."""
    pieces = ["四字句。", SENTENCE_B]
    short = FakeTTS()
    collect(
        TurnInput("hello"),
        deps_for(FakeLLM(pieces, delay=0.05), short, pool),
        pool=pool,
    )
    call = FakeTTS()
    collect(
        TurnInput("hello", voice_call=True),
        deps_for(FakeLLM(pieces, delay=0.05), call, pool),
        pool=pool,
    )
    assert short.texts[0] == "四字句。" + SENTENCE_B
    assert call.texts[0] == "四字句。"


def test_the_knobs_come_from_the_settings_when_the_host_says_nothing(monkeypatch):
    monkeypatch.setenv("ECHOTURN_TTS_CHUNK_CHARS", "11")
    monkeypatch.setenv("ECHOTURN_TTS_FIRST_CHARS", "3")
    policy = policy_from_dials()
    assert policy.chunk_chars == 11
    assert policy.first_chars == 3
