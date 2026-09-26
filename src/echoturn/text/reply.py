"""Reduce everything a model wrote into the text a person should read.

Two failure modes are worth the code below, and both are about text that was
never meant to be shown:

* Structured output. A prompt that asks for a JSON object gets it in the same
  stream as the prose, and a reply that carries ``{"mood": "warm"}`` is read
  aloud - or worse, shown in a message bubble. The object is removed and the
  prose around it is kept, wherever it stands: a model that writes its data in
  the middle of an answer has still written an answer.
* Reasoning. Providers increasingly put a chain of thought in the same field as
  the answer, wrapped in a tag or a fenced block. It is long, it is not an answer,
  and it is written for a reader who knows what is going on.

Only a ``{...}`` run that actually parses as a JSON object is removed, plus the
run that opens a line (or a quoted key) and never closes: a reply that stopped
mid-object left half a contract behind, and half a contract is not a sentence.
Braces in prose are common - quoting somebody, writing a formula - and cutting at
a brace without checking would delete a real sentence. The streaming path holds a
brace that may open an object until it closes and then asks the same question, so
the words on screen and the voice in the ear cannot disagree about what was data.
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
_JSON_HEAD = re.compile(r'\{\s*"')


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
    """Remove fenced blocks, and the data objects a model wrote into prose."""
    if _FENCED.search(text):
        return _FENCED.sub("", text)
    fence = _FENCE_OPEN.search(text)
    if fence:
        # An opening marker with no closing one. Either the reply was cut off or
        # the model never finished the block; in both cases the text after it is
        # machine output, not prose.
        return text[: fence.start()]
    stripped = strip_data_objects(text)
    if not stripped.strip() and _is_only_objects(text):
        # The whole reply is structured output. An empty reply is a worse answer
        # than the object itself: a host that asked for one can still read this,
        # and there is no prose to protect either way.
        return text
    return cut_open_object(stripped)


def object_end(text: str, start: int) -> int | None:
    """Index just past the brace that closes the object opening at ``start``.

    Braces are counted, and quotes and backslash escapes are respected, because
    a JSON string may contain both. A newline is not a place to give up: a model
    that writes its data pretty-printed puts the closing brace on a line of its
    own, and a scan that stopped at the first newline would call the object
    unfinished and hand half of it to a reader.

    ``None`` means the braces have not balanced - yet, or ever.
    """
    if start < 0 or start >= len(text) or text[start] != "{":
        return None
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
        elif quoted and char == "\\":
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif not quoted and char == "{":
            depth += 1
        elif not quoted and char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def is_data_object(candidate: str) -> bool:
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


def strip_data_objects(text: str) -> str:
    """Remove every complete ``{...}`` that parses as a JSON object.

    From the left, one at a time, keeping everything between them: the prose in
    front of an object and the prose behind it are both the model talking. A
    brace that opens no object is left exactly where it was.
    """
    kept: list[str] = []
    index = 0
    while True:
        start = text.find("{", index)
        if start < 0:
            kept.append(text[index:])
            return "".join(kept)
        end = object_end(text, start)
        if end is None or not is_data_object(text[start:end]):
            # Not an object: keep the brace and look past it, so that text like
            # ``{not json at all}`` is one failed attempt rather than one per
            # character.
            kept.append(text[index : start + 1])
            index = start + 1
            continue
        kept.append(text[index:start])
        index = end
        # A model that writes its data inside a sentence usually leaves a space
        # on each side of it; removing the object must not leave two.
        if kept[-1].endswith((" ", "\t")) and text[index : index + 1] in (" ", "\t"):
            while text[index : index + 1] in (" ", "\t"):
                index += 1


def opens_data_object(text: str, start: int) -> bool:
    """Whether the brace at ``start`` can open a data object rather than prose.

    Two shapes count as machine output before anything has been parsed: a brace
    that opens a line, and a brace followed by a quoted key. The answer decides
    what the streaming path holds back for a moment and what is cut when a reply
    stops mid-brace, so it is pinned here once and asked from both places.
    Everything else - a formula, a quoted brace inside a sentence - is prose.
    """
    index = start
    while index > 0 and text[index - 1] in " \t":
        index -= 1
    if index == 0 or text[index - 1] == "\n":
        return True
    return _JSON_HEAD.match(text, start) is not None


def cut_open_object(text: str) -> str:
    """The text before a run that opened a brace and never closed it.

    :func:`strip_data_objects` handles the objects that finished. This is the
    other half of the same judgement: the reply stopped inside a brace run - the
    stream was cut, the turn hit a cap - and half of a contract must not be read
    out. Only a run :func:`opens_data_object` accepts is cut; an unbalanced brace
    inside a sentence is left alone, because a typo is as likely as data and the
    sentence is what a person is listening to.
    """
    index = 0
    while True:
        brace = text.find("{", index)
        if brace < 0:
            return text
        end = object_end(text, brace)
        if end is None:
            return text[:brace] if opens_data_object(text, brace) else text
        index = end


def _is_only_objects(text: str) -> bool:
    """Whether the reply is nothing but complete objects, one after another.

    A cut-off object does not count: the point of keeping the reply is that a
    host asked for structured output can still read it, and half of it is not
    readable either way.
    """
    rest = text.strip()
    if not rest.startswith("{"):
        return False
    found = False
    while rest.startswith("{"):
        end = object_end(rest, 0)
        if end is None or not is_data_object(rest[:end]):
            return False
        found = True
        rest = rest[end:].lstrip()
    return found and not rest
