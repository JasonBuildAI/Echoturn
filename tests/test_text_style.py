import dataclasses

import pytest

from echoturn.text.style import (
    TEXT_STYLE,
    VOICE_STYLE,
    SpeechStyle,
    get_style,
    is_voice,
    with_rules,
)


def test_unknown_names_fall_back_to_the_writing_style():
    assert get_style("nonsense") is TEXT_STYLE
    assert get_style(None) is TEXT_STYLE
    assert get_style("") is TEXT_STYLE


def test_style_names_are_case_insensitive():
    assert get_style(" VOICE ") is VOICE_STYLE


def test_a_style_object_passes_through():
    custom = SpeechStyle(name="custom", ellipsis_budget=0)
    assert get_style(custom) is custom


def test_voice_keeps_fillers_and_text_does_not():
    assert is_voice(VOICE_STYLE) is True
    assert is_voice(TEXT_STYLE) is False


def test_the_taste_rules_are_off_by_default():
    """They are a product decision; the mechanism is here, not the opinion."""
    assert TEXT_STYLE.fold_exclamation is False
    assert TEXT_STYLE.drop_emoji is False
    assert VOICE_STYLE.fold_exclamation is False
    assert VOICE_STYLE.drop_emoji is False


def test_with_rules_returns_a_copy_and_leaves_the_preset_alone():
    tweaked = with_rules(TEXT_STYLE, fold_exclamation=True)
    assert tweaked.fold_exclamation is True
    assert TEXT_STYLE.fold_exclamation is False
    with pytest.raises(dataclasses.FrozenInstanceError):
        tweaked.name = "other"
