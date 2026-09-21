import pytest

from audio_helpers import silence, tone
from echoturn.audio.resample import resample_pcm16
from echoturn.audio.wav import wav_seconds


def test_matching_rates_return_the_input_untouched():
    pcm = tone(200, 0.05)
    assert resample_pcm16(pcm, 24000, 24000) is pcm


def test_downsampling_shortens_the_audio():
    out = resample_pcm16(silence(1.0, 48000), 48000, 24000)
    assert len(out) == 24000 * 2


def test_upsampling_lengthens_the_audio():
    out = resample_pcm16(silence(1.0, 16000), 16000, 48000)
    assert len(out) == 48000 * 2


def test_the_duration_is_preserved_in_time():
    from echoturn.audio.wav import pcm16_to_wav

    pcm = silence(0.5, 48000)
    out = resample_pcm16(pcm, 48000, 16000)
    assert wav_seconds(pcm16_to_wav(out, 16000)) == 0.5


def test_a_constant_signal_stays_constant():
    pcm = silence(0.01, 24000)
    out = resample_pcm16(pcm, 24000, 16000)
    assert set(out) == {0}


def test_too_short_a_buffer_is_returned_as_is():
    assert resample_pcm16(b"\x01\x00", 24000, 16000) == b"\x01\x00"


def test_a_nonsense_rate_is_rejected():
    with pytest.raises(ValueError):
        resample_pcm16(b"\x00\x00" * 8, 0, 16000)
    with pytest.raises(ValueError):
        resample_pcm16(b"\x00\x00" * 8, 16000, -1)
