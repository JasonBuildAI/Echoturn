"""Split and reshape a finished reply into messages.

The number of messages is a property of the reply, not of the transport: the
history view, the spoken segments and the bubble count all read the same split.
"""
from __future__ import annotations

import re

from .separators import STRAY_SEP
from .stage import strip_stage_directions

# Separators as an empty-matching line, so a regular split does the work. Both
# forms are accepted here for the same reason they are accepted in the stream
# walk: models paragraph with blank lines far more often than with dashes.
_SEP_LINE = re.compile(r"(?m)^[ \t]*(?:[-—–=]{3,})?[ \t]*$")


def split_messages(text: str) -> list[str]:
    """Split ``text`` into messages, dropping parts that carry nothing."""
    out: list[str] = []
    for part in _SEP_LINE.split(str(text or "")):
        part = strip_stage_directions(part)
        part = STRAY_SEP.sub("", part)
        cleaned = part.strip()
        if cleaned:
            out.append(cleaned)
    return out


def shape_messages(text: str, max_n: int) -> list[str]:
    """Return at most ``max_n`` messages: merge when there are too many.

    Merging only ever joins two neighbouring messages, which always produces a
    sentence someone could have said. Splitting to reach a target is deliberately
    not implemented: half a sentence sent as its own message is still filler, and
    the number of messages is an upper bound rather than a promise.
    """
    parts = split_messages(text)
    if not parts:
        return []
    limit = max(1, int(max_n or 1))
    while len(parts) > limit:
        shortest = min(range(len(parts)), key=lambda i: len(parts[i]))
        neighbour = shortest - 1 if shortest > 0 else shortest + 1
        left, right = min(shortest, neighbour), max(shortest, neighbour)
        parts[left:left + 2] = [parts[left].rstrip() + "\n" + parts[right].lstrip()]
    return parts
