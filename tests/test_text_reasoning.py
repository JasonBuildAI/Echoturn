from echoturn.text.reasoning import has_reasoning, strip_reasoning


def test_plain_text_is_returned_unchanged():
    text = "It is raining again today."
    assert strip_reasoning(text) == text
    assert has_reasoning(text) is False


def test_reasoning_before_a_closing_tag_is_dropped():
    raw = "Let me think about the date. </think>It was a Tuesday."
    assert strip_reasoning(raw) == "It was a Tuesday."
    assert has_reasoning(raw) is True


def test_tag_variants_are_recognised():
    for tag in ("</think>", "</thinking>", "</THINK>", "</think >"):
        assert strip_reasoning(f"reasoning{tag}answer") == "answer"


def test_the_first_closing_tag_wins():
    """Reasoning precedes speech, so a later tag inside the answer must survive."""
    raw = "thinking</think>I can write </think> literally, as a word."
    assert strip_reasoning(raw) == "I can write </think> literally, as a word."


def test_an_unclosed_tag_drops_the_tail():
    raw = "Sure thing. <think about it"
    assert strip_reasoning(raw) == "Sure thing. "


def test_a_lone_opening_tag_drops_everything_after_it():
    assert strip_reasoning("answer <thinking>still going") == "answer "


def test_whitespace_after_the_tag_does_not_lead_the_sentence():
    assert strip_reasoning("hmm</think>   hello") == "hello"


def test_empty_input_is_empty_output():
    assert strip_reasoning("") == ""
    assert strip_reasoning(None) == ""
    assert has_reasoning(None) is False
