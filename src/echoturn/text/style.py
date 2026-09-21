"""Speech styles: how much verbal tic a reply is allowed to keep.

A spoken reply and a written reply should not be cleaned the same way. Filler
words ("mm", "well") carry rhythm and social work in speech, and removing every
one of them makes a voice sound clipped; in writing the same words read as
vague. So the pipeline takes a style object rather than a boolean.

The style is also where *taste* lives, which is why the character rules below
default to off. Whether to fold exclamation marks or strip emoji is a product
decision, not a property of the pipeline - turn it on if you want it, and the
mechanism is here so you do not have to reimplement it.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

# Filler words a reply may open with. Kept short on purpose: this is a budget for
# hesitation sounds, not a dictionary.
DEFAULT_FILLERS: tuple[str, ...] = ("那个", "嗯", "唔", "呃", "哦", "诶", "啊", "哎")


@dataclass(frozen=True)
class SpeechStyle:
    """How a reply is cleaned before it is shown and before it is spoken."""

    name: str = "text"
    # How many ellipsis runs may survive one reply. One reads as hesitation; the
    # second one reads as a template.
    ellipsis_budget: int = 1
    # How many trailing tildes may survive one reply. Voice keeps one as a
    # drawn-out ending; writing keeps none, where a tilde reads as insincere.
    tilde_budget: int = 0
    # Keep at most one leading filler per message. This is the whole difference
    # between "speech" and "writing" for this layer.
    keep_one_filler: bool = False
    fillers: tuple[str, ...] = DEFAULT_FILLERS
    # Off by default: a taste, not a requirement. See the module docstring.
    fold_exclamation: bool = False
    drop_emoji: bool = False


TEXT_STYLE = SpeechStyle()

VOICE_STYLE = SpeechStyle(
    name="voice",
    ellipsis_budget=2,
    tilde_budget=1,
    keep_one_filler=True,
)

STYLES: dict[str, SpeechStyle] = {
    TEXT_STYLE.name: TEXT_STYLE,
    VOICE_STYLE.name: VOICE_STYLE,
}


def get_style(name: str | SpeechStyle | None) -> SpeechStyle:
    """Resolve a style by name. Anything unknown means the writing style."""
    if isinstance(name, SpeechStyle):
        return name
    return STYLES.get(str(name or "").strip().lower(), TEXT_STYLE)


def is_voice(style: SpeechStyle | str | None) -> bool:
    return get_style(style).keep_one_filler


def with_rules(style: SpeechStyle, **changes) -> SpeechStyle:
    """A copy of ``style`` with some fields replaced.

    Frozen dataclass plus an explicit helper keeps callers from mutating a shared
    preset and silently changing every other reply in the process.
    """
    return replace(style, **changes)
