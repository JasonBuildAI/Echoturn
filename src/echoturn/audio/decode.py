"""Decode a browser recording into the mono float samples the models expect.

Speech models are fed normalised floats in [-1, 1], not integers. Forgetting the
division by 32768 does not raise anything - it produces probabilities that are
quietly too low, which reads as "there was no speech" and is very hard to trace
back from the outside.

Only 16 kHz mono is accepted. Anything else returns None so the caller can fall
back honestly; resampling to guess would put audio through a model at the wrong
rate and produce confident nonsense.
"""
from __future__ import annotations

from array import array

from .wav import read_wav

# Probes run on every turn, so a long recording is truncated rather than walked.
MAX_SECONDS = 120
SCALE = 32768.0


def decode_16k_mono(data: bytes) -> array | None:
    """Return 16 kHz mono samples as ``array('f')``, or None for anything else."""
    info = read_wav(data)
    if info is None or info.sample_rate != 16000 or info.channels != 1:
        return None
    width = 2 if info.bits == 16 else 4 if info.bits == 32 else 0
    if not width:
        return None
    pcm = info.pcm[: 16000 * MAX_SECONDS * width]
    if info.bits == 16:
        raw = pcm[: len(pcm) // 2 * 2]
        return array(
            "f",
            (
                int.from_bytes(raw[i:i + 2], "little", signed=True) / SCALE
                for i in range(0, len(raw), 2)
            ),
        )
    # Both float32 and int32 are 32 bits wide and the format code is not parsed
    # here, so try both: a normalised float never leaves [-1, 1], while an int32
    # recording is far outside it. The magnitudes cannot be confused.
    floats = array("f")
    floats.frombytes(pcm[: len(pcm) // 4 * 4])
    if floats and max(abs(v) for v in floats[:: max(1, len(floats) // 1000)]) > 1.5:
        ints = array("i")
        ints.frombytes(pcm[: len(pcm) // 4 * 4])
        return array("f", (v / 2147483648.0 for v in ints))
    return floats


def to_float32(data: bytes) -> list[float]:
    """16-bit little-endian PCM as normalised floats."""
    raw = bytes(data or b"")
    n = len(raw) // 2
    return [int.from_bytes(raw[i * 2:i * 2 + 2], "little", signed=True) / SCALE
            for i in range(n)]
