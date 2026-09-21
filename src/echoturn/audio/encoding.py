"""Base64 helpers for moving audio through a text protocol.

Audio events travel as base64 WAV inside JSON. The decode side validates instead
of trusting, because the alternative is a stack trace from inside a provider call
for what is really a malformed request.
"""
from __future__ import annotations

import base64
import binascii


def to_base64(data: bytes) -> str:
    """Encode bytes for a JSON field."""
    return base64.b64encode(bytes(data or b"")).decode("ascii")


def from_base64(text: str) -> bytes:
    """Decode a base64 field, raising ValueError with a usable message."""
    raw = str(text or "").strip()
    if not raw:
        return b""
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("audio payload is not valid base64") from exc
