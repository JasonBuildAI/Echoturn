"""Last-pass normalisation of text immediately before synthesis.

Everything here has been measured, and each rule exists because the synthesis
model does something unreasonable without it. A doubled full stop is the
expensive one: the model reads it as the end of the utterance and silently drops
the rest of the sentence, so the listener hears a truncated reply with nothing
in the logs to explain it.

This sits closest to the provider on purpose. Callers that bypass the sentence
iterator - a direct "say this" endpoint, a test harness - still get a clean
string, and the whole-reply pass catches text that streaming could only see one
sentence at a time.
"""
from __future__ import annotations

import re

from .normalize import normalize_speech
from .reasoning import strip_reasoning
from .stage import strip_stage_directions
from .style import TEXT_STYLE, SpeechStyle

# Line breaks and tabs have no spoken equivalent; the model reads them as an
# unexplained pause. Leading spaces on a line cost audio as well.
_WHITESPACE = re.compile(r"[\r\n\t]+")
_SPACES = re.compile(r"[ ]{2,}")
# Collapse a punctuation mark repeated on itself. An ellipsis is deliberately
# absent: it is limited per reply, not collapsed here.
_DUPLICATE = re.compile(r"([。！？!?，、；;])(\1)+")


def prepare_for_tts(text: str, style: SpeechStyle | str | None = TEXT_STYLE) -> str:
    """Return the string to hand to a synthesis provider."""
    s = strip_reasoning(str(text or ""))
    s = strip_stage_directions(s)
    s = _WHITESPACE.sub("", s)
    s = _SPACES.sub(" ", s)
    s = _DUPLICATE.sub(r"\1", s)
    return normalize_speech(s, style).strip()
