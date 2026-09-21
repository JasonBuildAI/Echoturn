"""Limit repeated punctuation, and optionally remove decorative characters.

Two different jobs live here because they share one rule: only punctuation and
symbols are touched, never a word of content. A cleaner that can delete meaning
is a cleaner that can empty someone's reply, so the invariant is enforced by
construction rather than by care.
"""
from __future__ import annotations

import re

# "..." in its several typographic spellings. Written as a fragment so the same
# definition can be reused inside the leading-filler patterns.
ELLIPSIS = r"(?:…{1,3}|\.{3}|⋯+)"
ELLIPSIS_RUN = re.compile(ELLIPSIS)
_TILDE_RUN = re.compile(r"[~～]+")

_EXCLAIM = re.compile(r"[。，、；;：,？?]*[！!]+[？?]?")
_EMOJI = re.compile("[\u2600-\u27bf\U0001F000-\U0001FAFF\ufe0f\u20e3]+")
_KAOMOJI = re.compile(
    r"[\^＾]{1,2}[-_]?[\^＾]{1,2}"          # ^_^  ^-^
    r"|[>＞<＜]{1,2}[-_]?[<＜>＞]{1,2}"       # >_<  ><
    r"|[Tt][-_.][Tt]"                      # T_T  T.T
    r"|[oO0][rR][zZ]"                      # orz
    r"|[Oo][Tt][Zz]"                       # OTZ
)
# A comma left dangling in front of another punctuation mark, which is what
# removing something in the middle of a sentence leaves behind. A comma at the
# very end of the text is *not* touched: a sentence cut at a soft boundary ends
# with one, and eating it would mean the split no longer reconstructs the text.
_DANGLING_COMMA = re.compile(r"[，,](?=[。！？，、；;.!?])")


def cap_ellipsis(text: str, budget: int = 1) -> str:
    """Keep at most ``budget`` ellipsis runs in ``text``.

    A run that is dropped mid-sentence is replaced by a comma so the sentence
    does not lose its only pause, and a run that sits at a sentence end simply
    goes. Nothing else changes: this can shorten a reply, never gut it.
    """
    s = str(text or "")
    left = max(0, int(budget))
    out: list[str] = []
    pos = 0
    for match in ELLIPSIS_RUN.finditer(s):
        if left > 0:
            left -= 1
            continue
        out.append(s[pos:match.start()])
        before = "".join(out).rstrip()[-1:]
        after = s[match.end():].lstrip()[:1]
        if before in "。！？，、；;.!?" or not after or after in "。！？，、；;,.!?…":
            out.append("")
        else:
            out.append("，")
        pos = match.end()
    out.append(s[pos:])
    return _DANGLING_COMMA.sub("", "".join(out))


def cap_tilde(text: str, budget: int = 0) -> str:
    """Keep at most ``budget`` tildes, and only where one means a drawn-out end.

    A tilde is kept only when the next character ends the sentence (or the text).
    A mid-sentence tilde is decoration in every style, so the budget is spent on
    the one that can be heard as a trailing note rather than on an ornament.
    """
    s = str(text or "")
    left = max(0, int(budget))
    out: list[str] = []
    pos = 0
    for match in _TILDE_RUN.finditer(s):
        after = s[match.end():match.end() + 1]
        at_tail = (not after) or after in "\n。！？…"
        if left > 0 and at_tail:
            left -= 1
            continue
        out.append(s[pos:match.start()])
        pos = match.end()
    out.append(s[pos:])
    return "".join(out)


def strip_decorations(
    text: str, *, fold_exclamation: bool = False, drop_emoji: bool = False
) -> str:
    """Optionally fold exclamation marks and drop emoji / kaomoji.

    Both switches are off by default: they encode a product's taste, not a rule
    the pipeline needs. Bare kaomoji and emoji are the only forms handled here -
    bracketed and asterisk-wrapped ones are already removed as stage directions,
    and doing it twice would give the two layers two different opinions.
    """
    s = str(text or "")
    if drop_emoji:
        s = _KAOMOJI.sub("", s)
        s = _EMOJI.sub("", s)
    if fold_exclamation:
        s = _EXCLAIM.sub("。", s)
    s = _DANGLING_COMMA.sub("", s)
    return re.sub(r"。。+", "。", s)
