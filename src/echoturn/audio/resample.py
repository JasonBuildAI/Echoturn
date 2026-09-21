"""Resample 16-bit PCM between sample rates.

Linear interpolation, in pure Python, on purpose: the transport resamples in the
browser, and this exists for the host that receives audio at one rate and needs
another - a compatibility shim rather than a signal-processing feature. It is not
good enough for music and is entirely fine for speech at these rates.
"""
from __future__ import annotations

import struct


def resample_pcm16(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Return ``pcm`` resampled from ``src_rate`` to ``dst_rate``.

    Identical rates return the input untouched, which keeps the common path from
    paying for a round trip through float arithmetic.
    """
    raw = bytes(pcm or b"")
    src, dst = int(src_rate), int(dst_rate)
    if src <= 0 or dst <= 0:
        raise ValueError("sample rates must be positive")
    if src == dst:
        return raw
    count = len(raw) // 2
    if count < 2:
        return raw
    samples = struct.unpack(f"<{count}h", raw[: count * 2])
    out_count = max(1, int(round(count * dst / src)))
    ratio = src / dst
    out = bytearray()
    for i in range(out_count):
        pos = i * ratio
        left = int(pos)
        right = min(left + 1, count - 1)
        frac = pos - left
        value = samples[left] + (samples[right] - samples[left]) * frac
        out += struct.pack("<h", max(-32768, min(32767, int(round(value)))))
    return bytes(out)
