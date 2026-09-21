import math

import pytest

from audio_helpers import silence, tone
from echoturn.audio import pitch
from echoturn.audio.pitch import clamp_target, measure_f0, semitone_distance
from echoturn.errors import MissingDependencyError


def test_an_octave_is_twelve_semitones():
    assert semitone_distance(121.0, 242.0) == pytest.approx(12.0)
    assert semitone_distance(242.0, 242.0) == 0.0
    assert semitone_distance(0.0, 242.0) == 0.0


def test_the_distance_has_a_direction():
    assert semitone_distance(250.0, 242.0) < 0
    assert semitone_distance(230.0, 242.0) > 0


def test_a_target_outside_the_voice_range_falls_back():
    assert clamp_target(1000.0) == pitch.DEFAULT_TARGET_HZ
    assert clamp_target(10.0) == pitch.DEFAULT_TARGET_HZ
    assert clamp_target(210.0) == 210.0


def test_a_steady_tone_is_measured_accurately():
    measured = measure_f0(tone(242.0, 0.5), 24000)
    assert measured == pytest.approx(242.0, rel=0.05)


def test_the_measurement_tracks_the_pitch_it_is_given():
    """Two tones an octave apart must not read as the same number."""
    low = measure_f0(tone(120.0, 0.5), 24000)
    high = measure_f0(tone(240.0, 0.5), 24000)
    assert low == pytest.approx(120.0, rel=0.05)
    assert high / low == pytest.approx(2.0, rel=0.1)


def test_silence_has_no_pitch_to_report():
    assert measure_f0(silence(0.5), 24000) == 0.0


def test_a_clip_too_short_to_judge_reports_nothing():
    assert measure_f0(tone(242.0, 0.1), 24000) == 0.0


def test_a_clip_is_pulled_toward_the_target():
    source = 200.0
    locked = pitch.lock_pitch(tone(source, 1.0), 24000, target_hz=242.0)
    after = measure_f0(locked, 24000)
    assert abs(after - 242.0) < abs(source - 242.0)
    assert after == pytest.approx(242.0, rel=0.05)


def test_locking_does_not_change_the_length():
    original = tone(200.0, 0.6)
    assert len(pitch.lock_pitch(original, 24000, target_hz=242.0)) == len(original)


def test_a_clip_already_on_target_is_not_touched():
    """Processing leaves its own artefact, so it is only used when it is needed."""
    original = tone(242.0, 0.6)
    assert pitch.lock_pitch(original, 24000, target_hz=242.0) == original


def test_an_unmeasurable_clip_is_passed_through():
    original = silence(0.6)
    assert pitch.lock_pitch(original, 24000) == original


def test_a_missing_numeric_stack_says_so_instead_of_doing_nothing(monkeypatch):
    def unavailable():
        raise MissingDependencyError("pitch and speed processing", "dsp", "numpy")

    monkeypatch.setattr(pitch, "numpy", unavailable)
    with pytest.raises(MissingDependencyError) as excinfo:
        measure_f0(tone(242.0, 0.6), 24000)
    assert "dsp" in str(excinfo.value)


def test_the_measured_value_is_a_plain_float():
    value = measure_f0(tone(200.0, 0.5), 24000)
    assert isinstance(value, float)
    assert not math.isnan(value)
