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


def test_prose_after_an_object_is_kept():
    """A model that writes its data mid-answer has still written an answer."""
    raw = "That sounds good.\n{\"mood\": \"warm\"}\nAnd I mean it."
    assert clean_reply(raw) == "That sounds good.\n\nAnd I mean it."


def test_an_object_written_inside_a_sentence_leaves_one_space_behind():
    raw = "I said {\"mood\": \"warm\"} and meant it."
    assert clean_reply(raw) == "I said and meant it."


def test_a_pretty_printed_object_is_one_object():
    raw = 'Here it is.\n{\n  "mood": "warm",\n  "topic": 3\n}\nDone.'
    assert clean_reply(raw) == "Here it is.\n\nDone."


def test_a_brace_inside_a_string_does_not_end_the_object():
    raw = 'Silence.\n{"note": "a } and a { inside"}\nThen prose.'
    assert clean_reply(raw) == "Silence.\n\nThen prose."


def test_a_real_newline_inside_a_string_is_still_an_object():
    """The field shape: a pretty-printed value the model let break its own line."""
    raw = 'Good.\n{"note": "two\nlines"}\nDone.'
    assert clean_reply(raw) == "Good.\n\nDone."


def test_a_nested_object_is_cut_whole():
    raw = 'Right.\n{"a": {"b": 1}}\nDone.'
    assert clean_reply(raw) == "Right.\n\nDone."


def test_a_trailing_object_with_a_stray_comma_is_still_cut():
    raw = "Fine by me.\n{\"mood\": \"warm\",}"
    assert clean_reply(raw) == "Fine by me."


def test_an_object_cut_off_mid_write_is_not_read_out():
    """Half a contract is machine output too; the prose in front of it is not."""
    assert clean_reply("Fine by me.\n{\"mood\": \"war") == "Fine by me."
    assert clean_reply("Fine by me.\n{") == "Fine by me."
    assert clean_reply('She said {"a": 1') == "She said"


def test_an_unclosed_brace_inside_prose_is_still_prose():
    """The other direction of the same judgement: a typo must not lose a sentence."""
    raw = "The set {1, 2, 3 has no closing brace."
    assert clean_reply(raw) == raw


def test_braces_in_prose_are_not_mistaken_for_data():
    """The cut is only allowed when the object actually parses."""
    raw = "She wrote {not json at all} and left it there."
    assert clean_reply(raw) == raw


def test_a_reply_that_is_only_an_object_is_left_alone():
    """Nothing to keep means there is nothing to gain by cutting."""
    raw = "{\"mood\": \"warm\"}"
    assert clean_reply(raw) == raw


def test_a_reply_that_is_only_a_half_written_object_is_cut():
    """A cut-off object is not readable by a host either, so it is not kept."""
    assert clean_reply('{"mood": "war') == ""


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
