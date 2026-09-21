import numpy as np
import pytest

from audio_helpers import tone
from echoturn.audio import _phase


def as_samples(pcm):
    return np.frombuffer(pcm, dtype="<i2").astype(np.float64) / 32768.0


def test_the_transform_round_trips_without_changing_the_signal():
    """Analysis followed by synthesis is a no-op, so nothing else here is noise."""
    samples = as_samples(tone(242.0, 0.5))
    back = _phase.istft(np, _phase.stft(np, samples))
    assert np.allclose(back[: len(samples)], samples, atol=1e-6)


def test_the_transform_only_sees_whole_frames():
    samples = as_samples(tone(242.0, 0.5))
    spectrum = _phase.stft(np, samples)
    assert spectrum.shape[0] == _phase.N_FFT // 2 + 1
    assert spectrum.shape[1] == len(samples) // _phase.HOP + 1


def test_a_fitted_clip_is_exactly_the_length_asked_for():
    samples = np.arange(10.0)
    assert len(_phase.fit_length(np, samples, 4)) == 4
    padded = _phase.fit_length(np, samples, 12)
    assert len(padded) == 12
    assert list(padded[-2:]) == [0.0, 0.0]


def test_a_clip_shorter_than_one_window_is_still_transformed():
    """A clip below the window length is a real input, not an error case."""
    out = _phase.stretch(np, np.zeros(300), 2.0)
    assert len(out) > 0
    assert not np.isnan(out).any()


def test_a_stretch_lands_within_a_frame_of_the_requested_length():
    rate = 1.7
    samples = as_samples(tone(242.0, 1.0))
    stretched = _phase.stretch(np, samples, rate)
    assert len(stretched) == pytest.approx(len(samples) / rate, abs=_phase.HOP)


def test_shifting_a_pitch_does_not_change_the_length():
    samples = as_samples(tone(242.0, 0.5))
    shifted = _phase.pitch_shift(np, samples, 3.0)
    assert len(shifted) == pytest.approx(len(samples), abs=_phase.HOP)
