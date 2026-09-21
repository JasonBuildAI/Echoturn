from echoturn.text.stage import strip_stage_directions


def test_bracketed_actions_are_removed():
    assert strip_stage_directions("(tilts head) yes, of course") == "yes, of course"
    assert strip_stage_directions("（微微一偏头）好呀") == "好呀"
    assert strip_stage_directions("[sighs] fine.") == "fine."


def test_asterisk_emphasis_is_removed():
    assert strip_stage_directions("*nods* go on") == "go on"
    assert strip_stage_directions("**whispers** go on") == "go on"


def test_an_unclosed_bracket_at_the_end_is_removed():
    """Sentence splitting can cut an action in half; the remainder still leaks."""
    assert strip_stage_directions("yes (she pauses") == "yes"


def test_a_stray_closing_bracket_is_removed():
    assert strip_stage_directions(") yes") == "yes"


def test_quoted_speech_is_kept():
    assert strip_stage_directions("she said 「go」") == "she said 「go」"


def test_a_long_bracket_is_left_alone():
    """The 80-character cap keeps a stray bracket from eating a whole paragraph."""
    text = "(" + "x" * 120 + ")"
    assert strip_stage_directions(text) == text


def test_message_separators_survive():
    """They are structure for the message splitter, not decoration."""
    assert strip_stage_directions("first\n---\nsecond") == "first\n---\nsecond"


def test_repeated_spaces_are_collapsed():
    assert strip_stage_directions("a (x)   b") == "a b"
