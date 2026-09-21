import numpy as np
import pytest

from echoturn.endpoint import turn
from echoturn.endpoint.turn import WINDOW_SAMPLES, SmartTurn

RATE = 16000


class StubSession:
    """Answers with a fixed probability and records the features it was given."""

    def __init__(self, probability: float = 0.9) -> None:
        self.probability = probability
        self.features: list[np.ndarray] = []

    def run(self, _outputs, feeds):
        self.features.append(np.array(feeds["input_features"], copy=True))
        return np.array([[self.probability]], dtype=np.float32)


def judge(probability: float = 0.9, session=None):
    ready = session or StubSession(probability)
    return SmartTurn(path="definitely-not-here.onnx", session=ready)


def test_a_finished_sentence_reads_as_finished():
    assert judge(0.97).judge([0.1] * RATE)["complete"] is True


def test_an_unfinished_sentence_reads_as_unfinished():
    assert judge(0.06).judge([0.1] * RATE)["complete"] is False


def test_the_probability_comes_back_for_the_log():
    assert judge(0.23).judge([0.1] * RATE)["prob"] == pytest.approx(0.23, abs=0.01)


def test_there_is_no_answer_without_a_model():
    missing = SmartTurn(path="definitely-not-here.onnx")
    assert missing.judge([0.1] * RATE) is None
    assert "model file" in missing.last_error
    assert missing.ready() is False


def test_the_window_is_the_most_recent_eight_seconds():
    """The end of the audio has to land at the end of the window."""
    marker = np.arange(WINDOW_SAMPLES * 2, dtype=np.float32)
    window = judge().window(marker)
    assert np.array_equal(window, marker[-WINDOW_SAMPLES:])


def test_a_short_recording_is_padded_at_the_front():
    """Padding at the end would hand the model silence where the words are."""
    window = judge().window(np.ones(100, dtype=np.float32))
    assert window[-100:].sum() == pytest.approx(100.0)
    assert window[:-100].sum() == 0.0


def test_the_features_are_shaped_for_the_model():
    session = StubSession()
    judge(session=session).judge([0.2] * RATE)
    assert session.features[0].shape == (1, 80, 800)


def test_a_model_that_breaks_falls_back_instead_of_raising():
    class Broken:
        def run(self, _outputs, _feeds):
            raise RuntimeError("bad model file")

    broken = judge(session=Broken())
    assert broken.judge([0.1] * RATE) is None
    assert "bad model file" in broken.last_error


def test_the_threshold_is_where_it_says_it_is():
    assert turn.COMPLETE_THRESHOLD == 0.5
    assert judge(0.5).judge([0.1] * RATE)["complete"] is False
    assert judge(0.5001).judge([0.1] * RATE)["complete"] is True


def test_an_empty_recording_is_still_judged():
    assert judge().judge([]) is not None
