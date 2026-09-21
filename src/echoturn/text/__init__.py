"""Turning model output into something worth saying out loud."""

from .chunking import ChunkPolicy
from .fillers import strip_leading_filler, strip_leading_filler_keep_one
from .messages import shape_messages, split_messages
from .normalize import normalize_speech
from .punctuation import cap_ellipsis, cap_tilde, strip_decorations
from .reasoning import has_reasoning, strip_reasoning
from .sentences import iter_message_sentences, iter_sentences
from .separators import is_message_sep
from .speakable import is_speakable
from .stage import strip_stage_directions
from .style import (
    DEFAULT_FILLERS,
    STYLES,
    TEXT_STYLE,
    VOICE_STYLE,
    SpeechStyle,
    get_style,
    is_voice,
    with_rules,
)
from .tts import prepare_for_tts

__all__ = [
    "ChunkPolicy",
    "DEFAULT_FILLERS",
    "STYLES",
    "TEXT_STYLE",
    "VOICE_STYLE",
    "SpeechStyle",
    "cap_ellipsis",
    "cap_tilde",
    "get_style",
    "has_reasoning",
    "is_message_sep",
    "is_speakable",
    "is_voice",
    "iter_message_sentences",
    "iter_sentences",
    "normalize_speech",
    "prepare_for_tts",
    "shape_messages",
    "split_messages",
    "strip_decorations",
    "strip_leading_filler",
    "strip_leading_filler_keep_one",
    "strip_reasoning",
    "strip_stage_directions",
    "with_rules",
]
