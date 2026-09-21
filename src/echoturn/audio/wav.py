"""Read and write WAV containers without assuming a fixed header size.

Recordings made in a browser routinely carry a ``LIST`` chunk before the audio
data, so a reader that seeks to byte 44 lands inside metadata and returns
something that sounds like noise. Everything here walks the chunk list instead,
which is barely more code and cannot be wrong that way.

A duration that cannot be computed is reported as ``0.0`` rather than guessed.
Callers meter audio and bill for it; a plausible-looking wrong number is worse
than a missing one, because it gets recorded as a measurement.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

HEADER = 44


@dataclass(frozen=True)
class WavInfo:
    """What a WAV container says about itself."""

    sample_rate: int
    channels: int
    bits: int
    pcm: bytes

    @property
    def seconds(self) -> float:
        """Duration of the payload, or 0.0 when the format makes it unknowable."""
        frame = self.channels * (self.bits // 8)
        if not (self.pcm and self.sample_rate and frame):
            return 0.0
        return round(len(self.pcm) / (self.sample_rate * frame), 2)


def read_wav(data: bytes) -> WavInfo | None:
    """Parse ``data`` as a WAV container, or return None if it is not one.

    Chunks are walked in order and the format chunk is remembered before the data
    chunk is taken, because a data chunk that arrives first is not something to
    interpret blind.
    """
    raw = bytes(data or b"")
    if len(raw) < HEADER or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        return None
    rate = channels = bits = 0
    fmt_seen = False
    pcm: bytes | None = None
    i = 12
    while i + 8 <= len(raw):
        chunk_id = raw[i:i + 4]
        size = int.from_bytes(raw[i + 4:i + 8], "little")
        body = raw[i + 8:i + 8 + size]
        if chunk_id == b"fmt " and size >= 16:
            channels = int.from_bytes(body[2:4], "little")
            rate = int.from_bytes(body[4:8], "little")
            bits = int.from_bytes(body[14:16], "little")
            fmt_seen = True
        elif chunk_id == b"data" and fmt_seen:
            pcm = body if size else raw[i + 8:]
            break
        i += 8 + size + (size & 1)          # chunks are padded to even sizes
    if pcm is None or not (rate and channels and bits):
        return None
    return WavInfo(sample_rate=rate, channels=channels, bits=bits, pcm=pcm)


def wav_seconds(data: bytes) -> float:
    """Duration of a WAV payload in seconds, or 0.0 when it cannot be told."""
    info = read_wav(data)
    return info.seconds if info else 0.0


def pcm16_to_wav(pcm: bytes, sample_rate: int = 24000) -> bytes:
    """Wrap 16-bit little-endian mono PCM in the smallest valid WAV header."""
    body = bytes(pcm or b"")
    rate = int(sample_rate)
    header = (
        b"RIFF"
        + struct.pack("<I", 36 + len(body))
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
        + b"data"
        + struct.pack("<I", len(body))
    )
    return header + body
