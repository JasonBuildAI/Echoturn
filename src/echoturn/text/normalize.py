"""Clean a whole reply in one pass, without touching its structure.

This is the single definition of "what the reply looks like after cleaning", and
both the path that displays it and the path that speaks it go through it. Two
definitions would drift, and the failure mode of that drift is the worst kind:
the words on screen and the voice in the ear disagree, with nothing to point at.

Structure is preserved. Blank lines and dash lines separate messages, and the
message index that drives ordering, synthesis chunking and filler budgeting is
derived from them - so the line structure is data, not formatting.
"""
from __future__ import annotations

from .fillers import strip_leading_filler, strip_leading_filler_keep_one
from .punctuation import cap_ellipsis, cap_tilde, strip_decorations
from .separators import is_message_sep
from .style import TEXT_STYLE, SpeechStyle, get_style


def normalize_speech(text: str, style: SpeechStyle | str | None = TEXT_STYLE) -> str:
    """Clean ``text`` according to ``style``.

    Per line: remove a leading filler. In the spoken style the filler budget is
    per message, so the first line of a message may keep one and later lines of
    the same message may not - which is why the budget is counted here, where
    message boundaries are visible, and not in the sentence iterator.

    Per reply: limit ellipsis runs, limit tildes, and apply the optional
    character rules.
    """
    st = get_style(style)
    out: list[str] = []
    kept_in_message = False
    for line in str(text or "").split("\n"):
        if is_message_sep(line):
            kept_in_message = False          # a new message may spend the budget
            out.append(line)
            continue
        if not st.keep_one_filler or kept_in_message:
            out.append(strip_leading_filler(line, fillers=st.fillers))
            continue
        cleaned, kept = strip_leading_filler_keep_one(line, fillers=st.fillers)
        kept_in_message = kept
        out.append(cleaned)

    joined = cap_ellipsis("\n".join(out), st.ellipsis_budget)
    joined = cap_tilde(joined, st.tilde_budget)
    return strip_decorations(
        joined,
        fold_exclamation=st.fold_exclamation,
        drop_emoji=st.drop_emoji,
    )
