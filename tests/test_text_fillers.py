from echoturn.text.fillers import strip_leading_filler, strip_leading_filler_keep_one


def test_a_filler_plus_a_pause_is_removed():
    assert strip_leading_filler("嗯……来了") == "来了"
    assert strip_leading_filler("……来了") == "来了"


def test_a_plain_filler_without_a_pause_survives():
    """A short acknowledgement is an ordinary reply, not a tic."""
    assert strip_leading_filler("嗯，我知道了") == "嗯，我知道了"


def test_a_mid_sentence_ellipsis_is_content():
    assert strip_leading_filler("我画了……还是不对") == "我画了……还是不对"


def test_a_reply_that_is_only_a_pause_is_left_alone():
    """It is a deliberate empty beat; removing it would leave a hole."""
    assert strip_leading_filler("……") == "……"


def test_keeping_one_filler_reports_that_it_kept_one():
    text, kept = strip_leading_filler_keep_one("嗯……来了")
    assert (text, kept) == ("嗯……来了", True)


def test_repeated_fillers_collapse_to_one():
    text, kept = strip_leading_filler_keep_one("嗯……嗯……来了")
    assert (text, kept) == ("嗯……来了", True)


def test_a_bare_pause_lead_is_dropped_in_both_modes():
    assert strip_leading_filler_keep_one("……来了") == ("来了", False)


def test_the_keep_one_helper_falls_back_when_there_is_nothing_to_keep():
    text, kept = strip_leading_filler_keep_one("来了")
    assert (text, kept) == ("来了", False)


def test_custom_filler_lists_are_honoured():
    text, kept = strip_leading_filler_keep_one("well, fine", fillers=("well",))
    assert (text, kept) == ("well, fine", True)
    assert strip_leading_filler("hmm... fine", fillers=("hmm",)) == "fine"


def test_a_message_that_is_only_a_filler_is_not_emptied():
    assert strip_leading_filler("嗯……") == "嗯……"
