from echoturn.text.normalize import normalize_speech
from echoturn.text.style import TEXT_STYLE, VOICE_STYLE


def test_a_filler_lead_is_removed_in_the_writing_style():
    """The bare pause goes; a short acknowledgement after it is ordinary speech."""
    assert normalize_speech("……嗯，来了", TEXT_STYLE) == "嗯，来了"


def test_the_spoken_style_keeps_one_filler_per_message():
    assert normalize_speech("嗯……来了", VOICE_STYLE) == "嗯……来了"


def test_the_filler_budget_resets_at_a_message_boundary():
    """Each message gets its own budget; that is the whole point of counting here."""
    text = "嗯……来了\n\n嗯……马上"
    assert normalize_speech(text, VOICE_STYLE) == text


def test_only_the_first_line_of_a_message_may_keep_a_filler():
    assert normalize_speech("嗯……来了\n嗯……马上", VOICE_STYLE) == "嗯……来了\n马上"


def test_line_structure_is_preserved():
    """Message boundaries are data; a cleaner that eats them breaks the split."""
    assert "\n\n" in normalize_speech("一\n\n二", TEXT_STYLE)
    assert normalize_speech("一\n---\n二", TEXT_STYLE) == "一\n---\n二"


def test_the_ellipsis_budget_applies_to_the_whole_reply():
    assert normalize_speech("好……但是……再说", TEXT_STYLE) == "好……但是，再说"


def test_character_rules_stay_off_unless_asked_for():
    text = "真的！好耶，^_^"
    assert normalize_speech(text, TEXT_STYLE) == text
