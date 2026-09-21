import numpy as np
import pytest

from echoturn.endpoint import mel

RATE = mel.SAMPLE_RATE


def wave(seconds: float = 8.0, hz: float = 220.0, amplitude: float = 0.3) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    return (amplitude * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def test_the_features_have_the_shape_the_model_was_trained_on():
    assert mel.log_mel(wave()).shape == (mel.MELS, 800)


def test_a_short_recording_is_padded_to_the_full_window():
    assert mel.log_mel(wave(1.0)).shape == (mel.MELS, 800)


def test_a_long_recording_keeps_only_the_first_window():
    assert mel.log_mel(wave(20.0)).shape == (mel.MELS, 800)


def test_the_loudness_of_the_recording_does_not_change_the_features():
    """Normalisation is the difference between a 0.97 and a coin toss."""
    quiet = mel.log_mel(wave(amplitude=0.05))
    loud = mel.log_mel(wave(amplitude=0.9))
    assert np.allclose(quiet, loud, atol=1e-4)


def test_silence_produces_finite_features():
    """A NaN would propagate into the model and out the other side."""
    out = mel.log_mel(np.zeros(RATE * 8, dtype=np.float32))
    assert np.isfinite(out).all()


def test_the_features_stay_inside_a_bounded_range():
    """Bounded, not tiny: the top is set by the loudest band and the log scale."""
    out = mel.log_mel(wave())
    assert out.min() >= -1.01
    assert out.max() <= 2.0


def test_the_mel_scale_round_trips():
    assert mel.mel_to_hz(mel.hz_to_mel(1000.0))[0] == pytest.approx(1000.0)
    assert mel.mel_to_hz(mel.hz_to_mel(300.0))[0] == pytest.approx(300.0)
    assert mel.mel_to_hz(mel.hz_to_mel(7000.0))[0] == pytest.approx(7000.0)


def test_the_mel_scale_is_linear_below_a_kilohertz_and_curved_above_it():
    below = mel.hz_to_mel(500.0)[0] - mel.hz_to_mel(0.0)[0]
    assert below == pytest.approx(mel.hz_to_mel(1000.0)[0] - mel.hz_to_mel(500.0)[0])
    assert mel.hz_to_mel(8000.0)[0] < 8 * mel.hz_to_mel(1000.0)[0]


def test_every_filter_covers_some_band_and_none_of_them_is_negative():
    bank = mel.filterbank()
    assert bank.shape == (mel.WINDOW // 2 + 1, mel.MELS)
    assert (bank >= 0).all()
    assert (bank.sum(axis=0) > 0).all()


def test_the_window_is_periodic_rather_than_symmetric():
    assert len(mel.WINDOW_FUNCTION) == mel.WINDOW
    assert mel.WINDOW_FUNCTION[0] == pytest.approx(0.0, abs=1e-9)


def test_a_tone_shows_up_in_the_bands_it_belongs_to():
    """Low notes and high notes must not land in the same place."""
    low = mel.log_mel(wave(1.0, hz=200.0)).mean(axis=1)
    high = mel.log_mel(wave(1.0, hz=3000.0)).mean(axis=1)
    assert int(np.argmax(low)) < int(np.argmax(high))
