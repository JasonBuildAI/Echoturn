from echoturn.text import TEXT_STYLE, VOICE_STYLE
from echoturn.text.reply import clean_reply


def test_plain_prose_comes_through_unchanged():
    assert clean_reply("I am here, and I was listening.") == (
        "I am here, and I was listening."
    )


def test_a_fenced_block_is_dropped_and_the_prose_kept():
    raw = "Here is the answer.\n\n```json\n{\"mood\": \"warm\"}\n```\n"
    assert clean_reply(raw) == "Here is the answer."


def test_an_unclosed_fence_cuts_the_tail():
    assert clean_reply("As I was saying.\n```json\n{\"mood\":") == "As I was saying."


def test_a_trailing_bare_object_is_cut_before_it():
    raw = "That sounds good to me.\n{\"mood\": \"warm\", \"topic\": 3}"
    assert clean_reply(raw) == "That sounds good to me."


def test_a_trailing_object_with_a_stray_comma_is_still_cut():
    raw = "Fine by me.\n{\"mood\": \"warm\",}"
    assert clean_reply(raw) == "Fine by me."


def test_braces_in_prose_are_not_mistaken_for_data():
    """The cut is only allowed when the object actually parses."""
    raw = "She wrote {not json at all} and left it there."
    assert clean_reply(raw) == raw


def test_a_reply_that_is_only_an_object_is_left_alone():
    """Nothing to keep means there is nothing to gain by cutting."""
    raw = "{\"mood\": \"warm\"}"
    assert clean_reply(raw) == raw


def test_reasoning_is_removed_before_the_object_hunt():
    raw = "He asked twice, so answer. </think>The answer is yes."
    assert clean_reply(raw) == "The answer is yes."


def test_the_style_decides_what_happens_to_a_leading_filler():
    raw = "嗯……我在"
    assert clean_reply(raw, TEXT_STYLE) == "我在"
    assert clean_reply(raw, VOICE_STYLE) == "嗯……我在"


def test_runs_of_blank_lines_are_collapsed_to_one_separator():
    assert clean_reply("One.\n\n\n\nTwo.") == "One.\n\nTwo."


def test_nothing_at_all_is_an_empty_string():
    assert clean_reply("") == ""
    assert clean_reply(None) == ""
