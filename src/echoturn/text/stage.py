"""Remove stage directions - written actions - from text that will be spoken.

This is the classic voice-assistant bug: the model decorates an answer with an
action in brackets, the text goes straight to synthesis, and the listener hears
the bracketed words read out in full. Nothing in the pipeline can tell the
difference between an action and a sentence, so it has to be removed by shape.

Two shapes are covered: brackets (half- and full-width, square and lenticular)
and asterisk emphasis. Quoted speech in guillemets is deliberately left alone -
that is content, not decoration.

Message separators are deliberately *not* touched here: they are structure used
later to split a reply into several messages. Removing them at this stage would
leave nothing to split on.
"""
from __future__ import annotations

import re

# A bracketed span. Capped at 80 characters so a stray opening bracket cannot
# swallow the rest of a paragraph; nested brackets are not handled because
# models essentially never write them.
_BRACKET = re.compile(r"[（(【\[〔][^（()）【\[\]〔〕\n]{0,80}[）)】\]〕]")
# Asterisk emphasis, one or two asterisks on each side.
_STAR = re.compile(r"\*{1,2}[^*\n]{0,80}\*{1,2}")
# An opening bracket that never closes: this happens when a sentence boundary
# falls inside the action, so the halves arrive as separate pieces and neither
# looks bracketed any more.
_UNCLOSED = re.compile(r"[（(【\[〔][^（()）【\[\]〔〕\n]*$")
# A stray closing bracket with no opening one, the mirror of the above.
_STRAY_CLOSE = re.compile(r"^[）)】\]〕]+")
_MULTISPACE = re.compile(r"[ \t]{2,}")


def strip_stage_directions(text: str) -> str:
    """Return ``text`` with written actions and emphasis markers removed."""
    out = _BRACKET.sub("", str(text or ""))
    out = _STAR.sub("", out)
    out = _UNCLOSED.sub("", out)
    out = _STRAY_CLOSE.sub("", out)
    out = _MULTISPACE.sub(" ", out)
    return out.strip()
