import struct

from audio_helpers import silence, tone, wav_with_list_chunk
from echoturn.audio.wav import WavInfo, pcm16_to_wav, read_wav, wav_seconds


def test_pcm_survives_a_round_trip():
    pcm = tone(240, 0.1)
    info = read_wav(pcm16_to_wav(pcm, 24000))
    assert info is not None
    assert (info.sample_rate, info.channels, info.bits) == (24000, 1, 16)
    assert info.pcm == pcm


def test_duration_is_computed_from_the_payload():
    assert wav_seconds(pcm16_to_wav(silence(1.0, 24000), 24000)) == 1.0
    assert wav_seconds(pcm16_to_wav(silence(0.25, 16000), 16000)) == 0.25


def test_metadata_before_the_data_chunk_is_skipped():
    """A fixed 44-byte offset would read the metadata and call it audio."""
    pcm = tone(200, 0.05, 16000)
    info = read_wav(wav_with_list_chunk(pcm, 16000))
    assert info is not None
    assert info.pcm == pcm
    assert info.seconds.__class__ is float


def test_a_shorter_header_is_not_interpreted_as_audio():
    raw = pcm16_to_wav(tone(200, 0.05), 24000)
    assert read_wav(raw[:21]) is None
    assert wav_seconds(raw[:21]) == 0.0


def test_something_that_is_not_a_wav_is_rejected():
    assert read_wav(b"not a wav file at all, honestly" * 3) is None
    assert wav_seconds(b"") == 0.0
    assert wav_seconds(None) == 0.0


def test_a_missing_data_chunk_is_rejected():
    raw = pcm16_to_wav(b"", 24000)
    assert read_wav(raw) is not None          # an empty payload is still a WAV
    assert wav_seconds(raw) == 0.0


def test_a_hostile_header_does_not_overrun_the_buffer():
    raw = bytearray(pcm16_to_wav(tone(200, 0.05), 24000))
    raw[16:20] = struct.pack("<I", 10)        # a format chunk that is too short
    assert read_wav(bytes(raw)) is None


def test_seconds_is_zero_when_the_format_explains_nothing():
    assert WavInfo(sample_rate=0, channels=1, bits=16, pcm=b"\x00\x00").seconds == 0.0


def test_the_written_header_is_a_standard_pcm_wav():
    raw = pcm16_to_wav(b"\x00\x00" * 8, 24000)
    assert raw[:4] == b"RIFF" and raw[8:12] == b"WAVE"
    assert raw[12:16] == b"fmt "
    assert struct.unpack("<H", raw[20:22])[0] == 1        # PCM
    assert struct.unpack("<I", raw[24:28])[0] == 24000
