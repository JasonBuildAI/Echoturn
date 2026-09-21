import pytest

from audio_helpers import silence, tone
from echoturn.audio import stretch
from echoturn.audio.pitch import measure_f0
from echoturn.audio.stretch import clamp_rate, time_stretch
from echoturn.errors import MissingDependencyError


def test_a_normal_speed_is_kept():
    assert clamp_rate(1.0) == 1.0
    assert clamp_rate(1.4) == 1.4


def test_an_impossible_speed_falls_back():
    assert clamp_rate(0.1) == 1.0
    assert clamp_rate(9.0) == 1.0


def test_a_speed_that_is_not_a_number_is_refused_loudly():
    """Speed arrives as text from a config file, and the layer that knows the
    default for that file is the layer that parses it - not this one."""
    with pytest.raises(ValueError):
        clamp_rate("nonsense")


def test_a_rate_of_one_returns_the_input_untouched():
    pcm = silence(0.1)
    assert time_stretch(pcm, 1.0) == pcm


def test_an_unsupported_rate_is_refused_rather_than_clamped():
    with pytest.raises(ValueError):
        time_stretch(silence(0.1), 3.0)


def test_speeding_up_shortens_the_clip():
    pcm = tone(242.0, 1.0)
    assert len(time_stretch(pcm, 2.0)) == len(pcm) // 2


def test_slowing_down_lengthens_the_clip():
    pcm = tone(242.0, 0.5)
    assert len(time_stretch(pcm, 0.5)) == len(pcm) * 2


def test_the_speed_change_leaves_the_pitch_where_it_was():
    """The whole point: a faster voice is still the same voice."""
    original = tone(242.0, 1.0)
    faster = time_stretch(original, 1.5)
    assert measure_f0(faster, 24000) == pytest.approx(
        measure_f0(original, 24000), rel=0.05
    )


def test_silence_stays_silent():
    """A transform that turns silence into noise is worse than not having one."""
    out = time_stretch(silence(0.5), 1.5)
    assert set(out) == {0}


def test_a_missing_numeric_stack_says_so_instead_of_doing_nothing(monkeypatch):
    def unavailable():
        raise MissingDependencyError("pitch and speed processing", "dsp", "numpy")

    monkeypatch.setattr(stretch, "numpy", unavailable)
    with pytest.raises(MissingDependencyError):
        time_stretch(silence(0.2), 1.5)
