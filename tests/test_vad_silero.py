import numpy as np
import pytest

from echoturn.vad import silero
from echoturn.vad.silero import BLOCK, CONTEXT, SAMPLE_RATE, SileroVad


class StubSession:
    """Answers with a fixed probability per block and records what it was fed."""

    def __init__(self, probability: float = 0.9) -> None:
        self.probability = probability
        self.feeds: list[dict] = []

    def run(self, _outputs, feeds):
        self.feeds.append(
            {key: np.array(value, copy=True) for key, value in feeds.items()}
        )
        # The next state is the current one plus one, so a caller that forgets to
        # carry it forward gets a state that never moves.
        state = feeds["state"] + 1.0
        return np.array([[self.probability]], dtype=np.float32), state


def detector(probability: float = 0.9, session=None):
    ready = session or StubSession(probability)
    return SileroVad(path="definitely-not-here.onnx", session=ready)


def test_a_ready_detector_is_one_that_can_load():
    assert detector().ready()
    assert not SileroVad(path="definitely-not-here.onnx").ready()


def test_without_a_model_file_there_is_nothing_to_ask():
    missing = SileroVad(path="definitely-not-here.onnx")
    assert missing.report([0.0] * 1000) is None
    assert "model file" in missing.last_error


def test_speech_is_measured_in_milliseconds():
    report = detector().report([0.25] * SAMPLE_RATE)
    assert report["engine"] == "silero"
    assert report["speech_ms"] == pytest.approx(1000, abs=64)
    assert report["prob"] == pytest.approx(0.9, abs=0.01)


def test_silence_is_not_speech():
    assert detector(probability=0.01).report([0.0] * SAMPLE_RATE)["speech_ms"] == 0


def test_audio_is_offered_in_blocks_of_512_samples():
    """The model takes 512 at a time and says nothing about the rest."""
    session = StubSession()
    detector(session=session).report([0.1] * (SAMPLE_RATE + 100))
    assert len(session.feeds) == 32
    assert all(feed["input"].shape == (1, BLOCK + CONTEXT) for feed in session.feeds)


def test_each_call_carries_the_tail_of_the_previous_one():
    """Without those 64 samples the same recording scores near zero instead of high."""
    session = StubSession()
    samples = np.arange(SAMPLE_RATE, dtype=np.float32) / SAMPLE_RATE
    detector(session=session).report(samples)
    first, second = session.feeds[0]["input"][0], session.feeds[1]["input"][0]
    assert not first[:CONTEXT].any()
    assert np.array_equal(second[:CONTEXT], first[BLOCK:])


def test_the_recurrent_state_is_carried_between_calls():
    session = StubSession()
    detector(session=session).report([0.1] * SAMPLE_RATE)
    assert session.feeds[0]["state"].shape == silero.STATE_SHAPE
    assert session.feeds[0]["state"].sum() == 0.0
    assert session.feeds[1]["state"].sum() == 256.0
    assert session.feeds[2]["state"].sum() == 512.0


def test_the_sample_rate_is_told_to_the_model():
    session = StubSession()
    detector(session=session).report([0.1] * BLOCK)
    assert int(session.feeds[0]["sr"]) == SAMPLE_RATE


def test_a_failing_model_falls_back_instead_of_raising():
    class Broken:
        def run(self, _outputs, _feeds):
            raise RuntimeError("bad model file")

    broken = detector(session=Broken())
    assert broken.report([0.1] * SAMPLE_RATE) is None
    assert "bad model file" in broken.last_error


def test_an_empty_recording_asks_the_model_about_one_block():
    session = StubSession(probability=0.01)
    assert detector(session=session).report([])["speech_ms"] == 0
    assert len(session.feeds) == 1
