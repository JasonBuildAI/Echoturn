import pytest

from echoturn.vad.energy import DEFAULT_FLOOR, EnergyVad

RATE = 16000


def tone(seconds: float, amplitude: float = 0.3) -> list[float]:
    """Alternating samples at a fixed level: speech at that level, minus the words."""
    return [amplitude if i % 2 else -amplitude for i in range(int(seconds * RATE))]


def silence(seconds: float) -> list[float]:
    return [0.0] * int(seconds * RATE)


def test_a_loud_stretch_is_measured_as_speech():
    report = EnergyVad().report(tone(0.5))
    assert report["engine"] == "energy"
    assert report["speech_ms"] == pytest.approx(500, abs=64)


def test_quiet_audio_is_not_speech():
    assert EnergyVad().report(tone(0.5, amplitude=0.001))["speech_ms"] == 0


def test_the_level_is_reported_for_the_speech_it_found():
    assert EnergyVad().report(tone(0.5, amplitude=0.3))["level"] > DEFAULT_FLOOR


def test_silence_reports_no_level_at_all():
    assert EnergyVad().report(silence(0.5))["level"] == 0.0


def test_a_knock_is_not_counted_as_a_word():
    knock = tone(0.03) + silence(0.5)
    assert EnergyVad().report(knock)["speech_ms"] == 0


def test_a_pause_between_two_phrases_is_not_counted_as_speech():
    both = tone(0.4) + silence(0.4) + tone(0.4)
    assert EnergyVad().report(both)["speech_ms"] == pytest.approx(800, abs=64)


def test_the_floor_can_be_moved_for_a_noisy_room():
    noisy = tone(0.5, amplitude=0.05)
    assert EnergyVad().report(noisy)["speech_ms"] > 0
    assert EnergyVad(floor=0.2).report(noisy)["speech_ms"] == 0


def test_no_probability_is_reported_by_a_detector_that_has_none():
    """A level called "prob" would end up compared with the model's as if equal."""
    assert "prob" not in EnergyVad().report(tone(0.5))


def test_the_last_partial_block_is_measured_rather_than_dropped():
    assert len(EnergyVad().levels(silence(0.5) + [0.5])) == 16


def test_the_block_size_follows_the_sample_rate():
    assert EnergyVad(sample_rate=RATE).block == 512
    assert EnergyVad(sample_rate=8000).block == 256
