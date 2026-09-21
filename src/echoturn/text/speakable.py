"""Decide whether a piece of text is worth synthesising at all.

Streaming splits generate fragments that carry no content: a leftover full stop,
a lone ellipsis, the punctuation left behind after a stage direction is removed.
Sending those to synthesis costs a request and produces a strange noise, so
every path checks this predicate first.
"""
from __future__ import annotations

import re

# Everything that can be removed without removing meaning: whitespace, the
# punctuation of a dozen languages and scripts, and the emphasis characters.
_NOT_SPEECH = re.compile(
    r"[\s。！？!?，,、；;：:…—\-~～.·|/\\\"'“”‘’（）()\[\]【】〔〕*]+"
)


def is_speakable(text: str) -> bool:
    """True when something is left once punctuation and whitespace are gone."""
    return bool(_NOT_SPEECH.sub("", str(text or "")))
