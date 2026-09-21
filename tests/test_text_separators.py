from echoturn.text.separators import is_message_sep


def test_a_blank_line_is_a_separator():
    assert is_message_sep("") is True
    assert is_message_sep("   ") is True


def test_a_dash_line_is_a_separator():
    assert is_message_sep("---") is True
    assert is_message_sep("———") is True
    assert is_message_sep("===") is True
    assert is_message_sep("  ---  ") is True


def test_two_dashes_are_not_a_separator():
    assert is_message_sep("--") is False


def test_a_sentence_with_dashes_inside_is_not_a_separator():
    assert is_message_sep("等一下---我马上来") is False
    assert is_message_sep("真的一直在等") is False
