"""Strip the hesitation sounds a reply opens with.

Models trained on chat logs start sentences with a filler and an ellipsis, and
when that text is spoken it becomes a pause with nothing in it. Two levels of
diligence are needed, so there are two functions:

* :func:`strip_leading_filler` removes the lead outright - for writing, and as
  the fallback whenever a message has already spent its filler budget;
* :func:`strip_leading_filler_keep_one` keeps a single lead and reports whether
  it did, because "at most one per message" can only be decided by the layer
  that knows where messages begin.

Neither ever returns less than a placeholder. A reply that is nothing but
punctuation is a deliberate empty beat, and cleaning it away would leave a hole
in the interface where a message should be.
"""
from __future__ import annotations

import re

from .punctuation import ELLIPSIS
from .speakable import is_speakable
from .style import DEFAULT_FILLERS


def _alternation(fillers: tuple[str, ...]) -> str:
    return "|".join(re.escape(word) for word in fillers)


def _filler_with_pause(fillers: tuple[str, ...]) -> re.Pattern[str]:
    """A leading filler followed by an ellipsis, which is the stripping form.

    The ellipsis is required here on purpose: "mm, got it" is an ordinary reply
    and should survive, while "mm..." is the tic this exists to remove.
    """
    return re.compile(
        r"^\s*(?:" + _alternation(fillers) + r")\s*(?:" + ELLIPSIS + r")+\s*"
    )


def _pause_lead(fillers: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(r"^\s*(?:" + ELLIPSIS + r")+\s*")


def _optional_filler(fillers: tuple[str, ...]) -> re.Pattern[str]:
    """A leading filler with an optional pause - the keeping form."""
    return re.compile(
        r"^\s*(?:" + _alternation(fillers) + r")\s*(?:" + ELLIPSIS + r")?\s*"
    )


def _keep(original: str, cleaned: str) -> str:
    return cleaned if cleaned and is_speakable(cleaned) else original


def strip_leading_filler(
    text: str, *, fillers: tuple[str, ...] = DEFAULT_FILLERS
) -> str:
    """Remove a hesitation sound at the start, and nothing else.

    A bare ellipsis lead goes in every style: typed it suggests hesitation, and
    spoken it is a pause with nobody's voice in it. An ellipsis in the middle is
    content and is left alone.
    """
    t = str(text or "")
    out = _filler_with_pause(fillers).sub("", t, count=1)
    if out == t:
        out = _pause_lead(fillers).sub("", t, count=1)
    return _keep(t, out.lstrip())


def strip_leading_filler_keep_one(
    text: str, *, fillers: tuple[str, ...] = DEFAULT_FILLERS
) -> tuple[str, bool]:
    """Keep one leading filler, collapse repeats, and say whether one was kept.

    Returns ``(text, kept)``. The flag is what per-message budgeting counts, and
    it has exactly one definition - the counts elsewhere read this value rather
    than running their own pattern.
    """
    s = str(text or "")
    match = _optional_filler(fillers).match(s)
    if match:
        head = match.group(0).strip()
        rest = s[match.end():]
        while True:                       # "mm... mm..." collapses to one
            again = _optional_filler(fillers).match(rest)
            if not again:
                break
            rest = rest[again.end():]
        rest = rest.lstrip()
        if head and rest and is_speakable(rest):
            return head + rest, True
    return strip_leading_filler(s, fillers=fillers), False
