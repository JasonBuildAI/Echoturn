"""Synthetic audio used by the audio tests. Not a test module itself."""
from __future__ import annotations

import math
import struct


def tone(
    hz: float, seconds: float, rate: int = 24000, amplitude: float = 0.5
) -> bytes:
    """A sine wave as 16-bit little-endian PCM."""
    count = int(rate * seconds)
    peak = int(32767 * amplitude)
    return struct.pack(
        f"<{count}h",
        *(int(peak * math.sin(2 * math.pi * hz * i / rate)) for i in range(count)),
    )


def silence(seconds: float, rate: int = 24000) -> bytes:
    return b"\x00\x00" * int(rate * seconds)


def wav_with_list_chunk(
    pcm: bytes, rate: int, channels: int = 1, bits: int = 16
) -> bytes:
    """A WAV whose data chunk is preceded by metadata, as browsers write them."""
    payload = b"INFOIART" + b"\x1a\x00\x00\x00artist name\x00"
    body = (
        b"RIFF"
        + struct.pack("<I", 4 + (8 + 16) + (8 + len(payload)) + (8 + len(pcm)))
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, channels, rate, rate * channels * bits // 8,
                      channels * bits // 8, bits)
        + b"LIST"
        + struct.pack("<I", len(payload))
        + payload
        + b"data"
        + struct.pack("<I", len(pcm))
    )
    return body + pcm
