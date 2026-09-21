import struct

from audio_helpers import silence, tone, wav_with_list_chunk
from echoturn.audio import decode
from echoturn.audio.decode import decode_16k_mono, to_float32
from echoturn.audio.wav import pcm16_to_wav


def test_16k_mono_is_decoded_to_normalised_floats():
    pcm = struct.pack("<3h", 0, 16384, -32768)
    out = decode_16k_mono(pcm16_to_wav(pcm, 16000))
    assert out is not None
    assert list(out) == [0.0, 0.5, -1.0]


def test_the_wrong_sample_rate_is_refused_rather_than_guessed():
    assert decode_16k_mono(pcm16_to_wav(silence(0.1, 24000), 24000)) is None


def test_stereo_is_refused():
    pcm = silence(0.1, 16000) * 2
    assert decode_16k_mono(wav_with_list_chunk(pcm, 16000, channels=2)) is None


def test_metadata_before_the_data_chunk_still_decodes():
    pcm = tone(200, 0.05, 16000)
    assert decode_16k_mono(wav_with_list_chunk(pcm, 16000)) is not None


def test_float_samples_pass_through():
    payload = struct.pack("<3f", 0.0, 0.25, -0.5)
    wav = wav_with_list_chunk(payload, 16000, bits=32)
    out = decode_16k_mono(wav)
    assert out is not None
    assert list(out) == [0.0, 0.25, -0.5]


def test_integer_32_bit_samples_are_scaled_down():
    payload = struct.pack("<3i", 0, 2 ** 30, -2 ** 31)
    wav = wav_with_list_chunk(payload, 16000, bits=32)
    out = decode_16k_mono(wav)
    assert out is not None
    assert list(out) == [0.0, 0.5, -1.0]


def test_an_unsupported_bit_depth_is_refused():
    assert decode_16k_mono(wav_with_list_chunk(b"\x00" * 40, 16000, bits=8)) is None


def test_a_long_recording_is_truncated(monkeypatch):
    """Probes run every turn; the tail of a runaway recording is not worth walking."""
    monkeypatch.setattr(decode, "MAX_SECONDS", 1)
    out = decode_16k_mono(pcm16_to_wav(silence(3.0, 16000), 16000))
    assert out is not None
    assert len(out) == 16000


def test_to_float32_reads_little_endian_samples():
    assert to_float32(struct.pack("<2h", 16384, -16384)) == [0.5, -0.5]
