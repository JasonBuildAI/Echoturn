"""Reduce everything a model wrote into the text a person should read.

Two failure modes are worth the code below, and both are about text that was
never meant to be shown:

* Structured output. A prompt that asks for a trailing JSON object gets it in the
  same stream as the prose, and a reply that ends in ``{"mood": "warm"}`` is read
  aloud - or worse, shown in a message bubble.
* Reasoning. Providers increasingly put a chain of thought in the same field as
  the answer, wrapped in a tag or a fenced block. It is long, it is not an answer,
  and it is written for a reader who knows what is going on.

The cut for a trailing object only happens when the object actually parses as
JSON. Braces in prose are common - quoting somebody, writing a formula - and
truncating at the last brace without checking would delete a real sentence.

This runs on the finished reply rather than on the stream, because both problems
are properties of the whole text. A cut-off object and an unclosed fence are only
recognisable once you know where the text ends.
"""
from __future__ import annotations

import json
import re

from .normalize import normalize_speech
from .reasoning import strip_reasoning
from .stage import strip_stage_directions
from .style import TEXT_STYLE, SpeechStyle

_FENCED = re.compile(r"```(?:json)?\s*[\s\S]*?```")
_FENCE_OPEN = re.compile(r"```(?:json)?")
_BLANK_RUN = re.compile(r"\n{3,}")
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def clean_reply(raw: str, style: SpeechStyle | str | None = TEXT_STYLE) -> str:
    """The displayable form of a raw model reply.

    ``style`` must be the same one the sentence iterator and the synthesis path
    were given. If they differ, the words on screen and the voice in the ear
    disagree, and nothing anywhere reports it.
    """
    text = strip_reasoning(str(raw or ""))
    text = _drop_machine_text(text)
    text = strip_stage_directions(text)
    text = normalize_speech(text, style)
    return _BLANK_RUN.sub("\n\n", text).strip()


def _drop_machine_text(text: str) -> str:
    """Remove fenced blocks, and a trailing object that is clearly data."""
    if _FENCED.search(text):
        return _FENCED.sub("", text)
    fence = _FENCE_OPEN.search(text)
    if fence:
        # An opening marker with no closing one. Either the reply was cut off or
        # the model never finished the block; in both cases the text after it is
        # machine output, not prose.
        return text[: fence.start()]
    span = _trailing_object(text)
    return text[: span[0]] if span else text


def _balanced_span(text: str) -> tuple[int, int] | None:
    """The last complete *outermost* ``{...}`` pair, or None.

    Counting backwards from the final ``}`` finds the outermost pair rather than
    the innermost one, which is what makes the cut land before the object instead
    of inside it.
    """
    end = text.rfind("}")
    if end < 0:
        return None
    depth = 0
    for index in range(end, -1, -1):
        char = text[index]
        if char == "}":
            depth += 1
        elif char == "{":
            depth -= 1
            if depth == 0:
                return (index, end)
    return None


def _last_brace_span(text: str) -> tuple[int, int] | None:
    """Last ``{`` to last ``}``: the fallback when pairing does not close."""
    start, end = text.rfind("{"), text.rfind("}")
    return (start, end) if end > start >= 0 else None


def _loads_object(candidate: str) -> bool:
    """Whether ``candidate`` parses as a JSON object, allowing a trailing comma.

    The trailing comma is the most common way a model writes almost-valid JSON,
    and it is the one repair worth making before giving up on the cut.
    """
    for attempt in (candidate, _TRAILING_COMMA.sub(r"\1", candidate)):
        try:
            parsed = json.loads(attempt)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return True
    return False


def _trailing_object(text: str) -> tuple[int, int] | None:
    """Where a trailing JSON object starts, or None if there is not one."""
    for span in (_balanced_span(text), _last_brace_span(text)):
        if span is None or span[0] == 0:
            # Starting at zero means the whole reply is the object: there is no
            # prose in front of it to keep, so cutting would produce nothing.
            continue
        if _loads_object(text[span[0] : span[1] + 1]):
            return span
    return None
