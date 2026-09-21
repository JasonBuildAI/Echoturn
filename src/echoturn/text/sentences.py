"""Turn a stream of model output into speakable sentences.

Two boundaries, and the difference between them is the whole point:

* a *hard* boundary (a full stop, an exclamation or a question mark) means the
  sentence is over, so it can be sent to synthesis immediately;
* a *soft* boundary (a comma, a colon, an ellipsis) only becomes a cut when the
  buffer has grown too long, because waiting for the next full stop would mean
  several seconds of silence in the middle of a long sentence.

An ellipsis is deliberately a soft boundary even though it looks like an ending.
A model that habitually opens with one would otherwise have the first character
of every sentence cut off and synthesised on its own, which sounds like nothing
so much as a nervous tic.

Text inside a fenced code block is never spoken: it is a field for a program to
read, and reading it aloud is the classic voice-assistant embarrassment.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator

from .fillers import strip_leading_filler, strip_leading_filler_keep_one
from .punctuation import strip_decorations
from .reasoning import strip_reasoning
from .separators import SEP_PREFIX, STRAY_SEP, is_message_sep
from .speakable import is_speakable
from .stage import strip_stage_directions
from .style import TEXT_STYLE, SpeechStyle, get_style

HARD_BOUNDARY = "。！？!?"
SOFT_BOUNDARY = "，,、；;：…"
FENCE = "```"


class _Flush:
    """Sentinel: yield this between chunks to flush what is buffered.

    Without it a message boundary is only a newline, so text with no sentence
    punctuation in it keeps buffering across the boundary and the whole run is
    attributed to whichever message happens to be current when the buffer is
    finally written out. Yielding the sentinel makes the boundary explicit.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "FLUSH"


FLUSH = _Flush()


def _clean_piece(piece: str, style: SpeechStyle) -> str:
    """Clean one cut sentence; empty means "do not send this to synthesis".

    The leading filler is removed here as well as in the whole-reply pass,
    because this is the last point at which a fragment can be cleaned before it
    is spoken - and "the very first sound is a hesitation" is the most audible
    failure of all. In the spoken style the decision needs a message boundary,
    which this layer does not know about, so it leaves the lead alone and lets
    the message-aware layer decide.
    """
    text = strip_reasoning(piece)
    text = strip_stage_directions(text).strip()
    text = strip_decorations(
        text,
        fold_exclamation=style.fold_exclamation,
        drop_emoji=style.drop_emoji,
    )
    if not style.keep_one_filler:
        text = strip_leading_filler(text, fillers=style.fillers)
    return text if is_speakable(text) else ""


def iter_sentences(
    chunks: Iterable[str | _Flush],
    *,
    max_len: int = 50,
    style: SpeechStyle | str | None = TEXT_STYLE,
) -> Iterator[str]:
    """Yield sentences as they become complete, never waiting for the end."""
    st = get_style(style)
    buf = ""
    in_fence = False
    for chunk in chunks:
        if chunk is FLUSH:
            if in_fence:
                continue                     # a fence has no sentences to flush
            piece, buf = _clean_piece(buf, st), ""
            if piece:
                yield piece
            continue
        buf += chunk
        while buf:
            # Fence detection runs on the accumulated buffer, not on one chunk:
            # the marker can be split across chunks, and a chunk that both closes
            # a fence and carries the text after it must not lose that text.
            if in_fence:
                end = buf.find(FENCE)
                if end < 0:
                    buf = ""
                    break
                buf = buf[end + len(FENCE):]
                in_fence = False
                continue
            fence = buf.find(FENCE)
            if fence >= 0:
                head, buf = buf[:fence], buf[fence + len(FENCE):]
                head = _clean_piece(head, st)
                if head:
                    yield head
                in_fence = True
                continue
            hard = _first_index(buf, HARD_BOUNDARY)
            if hard >= 0:
                piece, buf = buf[:hard + 1], buf[hard + 1:]
                piece = _clean_piece(piece, st)
                if piece:
                    yield piece
                continue
            if len(buf) >= max_len:
                soft = _last_index(buf, SOFT_BOUNDARY)
                if soft > 0:
                    piece, buf = buf[:soft + 1], buf[soft + 1:]
                    piece = _clean_piece(piece, st)
                    if piece:
                        yield piece
                    continue
            break
    if not in_fence:
        tail = _clean_piece(buf, st)
        if tail:
            yield tail


def _first_index(text: str, chars: str) -> int:
    return min((i for i, ch in enumerate(text) if ch in chars), default=-1)


def _last_index(text: str, chars: str) -> int:
    return max((i for i, ch in enumerate(text) if ch in chars), default=-1)


def iter_message_sentences(
    chunks: Iterable[str],
    *,
    max_len: int = 50,
    style: SpeechStyle | str | None = TEXT_STYLE,
) -> Iterator[tuple[int, str]]:
    """Yield ``(message index, sentence)`` as a reply streams in.

    The message index starts at zero for the first message of the turn and is
    what the transport, the synthesis chunker and the filler budget all count
    on, so this walk and the whole-reply splitter must agree about boundaries.
    Both call :func:`echoturn.text.separators.is_message_sep`.
    """
    st = get_style(style)
    index = 0
    spent: set[int] = set()

    def pieces() -> Iterator[str]:
        nonlocal index
        buf = ""
        emitted = False          # this message already contains words
        line_open = False        # the last thing sent out was content, not a break
        for chunk in chunks:
            buf += chunk
            while buf:
                nl = buf.find("\n")
                if nl < 0:
                    # No line break yet. Hold only when the buffer might be the
                    # beginning of a separator; holding anything else would delay
                    # sentences until the whole reply is written, which is the
                    # difference between streaming and not streaming.
                    if SEP_PREFIX.match(buf):
                        break
                    line_open = True
                    yield buf
                    buf = ""
                    break
                line, buf = buf[:nl], buf[nl + 1:]
                if line == "" and line_open:
                    # This is the line break belonging to the previous line; the
                    # content went out long ago. It is not a blank line, and
                    # treating it as one would split one sentence into several
                    # messages whenever a token boundary lands on a newline.
                    line_open = False
                    yield "\n"
                    continue
                line_open = False
                if is_message_sep(line):
                    # Flush first and move the index afterwards, so a sentence
                    # still in the buffer belongs to the message it was written
                    # in rather than to the one that follows it.
                    yield FLUSH
                    if emitted:
                        index += 1
                        emitted = False
                    yield "\n"
                    continue
                emitted = True
                yield STRAY_SEP.sub("", line)
                yield "\n"
        if buf:
            yield buf

    for sentence in iter_sentences(pieces(), max_len=max_len, style=st):
        if not st.keep_one_filler or index in spent:
            yield index, strip_leading_filler(sentence, fillers=st.fillers)
            continue
        cleaned, kept = strip_leading_filler_keep_one(sentence, fillers=st.fillers)
        if kept:
            spent.add(index)
        yield index, cleaned
