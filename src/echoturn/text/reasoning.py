"""Remove model reasoning traces from text that is about to be spoken.

A model that thinks out loud writes its reasoning into the same string as the
answer. Left alone that reasoning is not merely displayed - it is synthesised,
played into someone's ear, and stored as if it had been said out loud. Worse,
once a stored reply is fed back as conversational context, the next turn copies
the habit: leaking becomes self-reinforcing rather than occasional.

The predicate lives here once. ``strip_reasoning`` decides what to remove and
``has_reasoning`` decides what to report, and both read the same patterns: two
copies would eventually disagree about what "had reasoning" means.

Only tags are used as evidence. Nothing here tries to guess whether prose
"looks like" reasoning - a closing tag cannot be something a speaker said, and
anything vaguer than that produces false positives on legitimate answers.
"""
from __future__ import annotations

import re

# A closing tag: what came before it is reasoning, whatever it looks like.
_THINK_CLOSE = re.compile(r"</think(?:ing)?\s*>", re.IGNORECASE)
# An opening tag. The closing ">" is optional on purpose: a truncated stream can
# cut the tag in half, and the half-written tag is still not something to speak.
_THINK_OPEN = re.compile(r"<think(?:ing)?\b[^>]*>?", re.IGNORECASE)


def strip_reasoning(text: str) -> str:
    """Return only the part of ``text`` that is meant to be heard.

    Three cases, and the third is the overwhelmingly common one:

    * a closing tag is present - drop everything up to and including it;
    * only an opening tag is present (truncated or never closed) - drop from it
      to the end, because there is no known point where the answer starts;
    * neither is present - return the input unchanged.

    The *first* closing tag wins rather than the last. Reasoning precedes the
    answer, so the first closing tag marks the start of speech; taking the last
    one would swallow the whole answer the moment the answer itself mentions a
    tag.
    """
    t = str(text or "")
    close = _THINK_CLOSE.search(t)
    if close:
        # Models usually emit a space after the tag ("</think> So anyway"). It
        # is not the first character of the sentence, so it goes.
        return t[close.end():].lstrip()
    opened = _THINK_OPEN.search(t)
    if opened:
        return t[:opened.start()]
    return t


def has_reasoning(text: str) -> bool:
    """Whether ``text`` carries a reasoning tag at all.

    Callers use this to record what happened during a turn. It shares the
    patterns with :func:`strip_reasoning` so that "we saw reasoning" and "we
    removed reasoning" can never drift apart.
    """
    t = str(text or "")
    return bool(_THINK_CLOSE.search(t) or _THINK_OPEN.search(t))
