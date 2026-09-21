from echoturn.text.sentences import FLUSH, iter_message_sentences, iter_sentences


def test_a_full_stop_ends_a_sentence_immediately():
    assert list(iter_sentences(["你好。", "我很好。"])) == ["你好。", "我很好。"]


def test_an_unfinished_buffer_is_held_back():
    assert list(iter_sentences(["你好"])) == ["你好"]


def test_an_ascii_full_stop_is_not_an_ending():
    """It reads like one and the docstring calls the ending "a full stop".

    The endings are the ones the model is written to use, so a reply in English
    is one long piece rather than several sentences. Pinned rather than fixed:
    the chunk thresholds were measured against this, and widening the set is a
    decision with a number attached, not a punctuation tidy-up.
    """
    assert list(iter_sentences(["One sentence. Another one."])) == [
        "One sentence. Another one."
    ]


def test_a_question_mark_ends_a_sentence_in_either_script():
    assert list(iter_sentences(["真的吗？", "Yes?"])) == ["真的吗？", "Yes?"]


def test_an_ellipsis_is_not_a_hard_boundary():
    """Otherwise a model that opens with one has a single character spoken alone."""
    out = list(iter_sentences(["……嗯，我想想。"]))
    assert out == ["嗯，我想想。"]


def test_a_long_buffer_is_cut_at_the_last_soft_boundary():
    text = "这是一句很长的话，" * 3 + "后面还没结束"
    out = list(iter_sentences([text], max_len=20))
    assert out[0].endswith("，")
    assert "".join(out) == text


def test_a_leading_soft_boundary_is_not_a_cut_point():
    out = list(iter_sentences(["，" + "字" * 30], max_len=10))
    assert out == ["，" + "字" * 30]


def test_fenced_content_is_never_spoken():
    chunks = ["好呀。```json\n{\"a\": 1}\n```然后呢。"]
    assert list(iter_sentences(chunks)) == ["好呀。", "然后呢。"]


def test_a_fence_split_across_chunks_is_still_detected():
    assert list(iter_sentences(["好。`", "``x```", "然后。"])) == ["好。", "然后。"]


def test_text_after_a_closing_fence_is_not_swallowed():
    """Regression: dropping the whole chunk lost the sentence after the fence."""
    assert list(iter_sentences(["```{\"a\": 1}```顺手说一句。"])) == ["顺手说一句。"]


def test_stage_directions_are_removed_before_speaking():
    assert list(iter_sentences(["（抬头）好呀。"])) == ["好呀。"]


def test_a_piece_that_is_only_stage_direction_is_dropped():
    assert list(iter_sentences(["（抬头）。"])) == []


def test_reasoning_is_stripped_inside_a_piece():
    assert list(iter_sentences(["想想。 </think>好呀。"])) == ["想想。", "好呀。"]


def test_flush_emits_the_buffer_as_a_sentence():
    assert list(iter_sentences(["没有标点", FLUSH])) == ["没有标点"]


def test_flush_inside_a_fence_emits_nothing():
    assert list(iter_sentences(["```code", FLUSH, "```好。"])) == ["好。"]


def test_message_index_starts_at_zero():
    assert [i for i, _ in iter_message_sentences(["好呀。"])] == [0]


def test_a_blank_line_advances_the_message_index():
    out = list(iter_message_sentences(["一。\n\n二。"]))
    assert out == [(0, "一。"), (1, "二。")]


def test_a_dash_line_advances_the_message_index():
    out = list(iter_message_sentences(["一。\n---\n二。"]))
    assert out == [(0, "一。"), (1, "二。")]


def test_a_plain_line_break_does_not_advance_the_index():
    """Models wrap lines inside one message; that is not a new message."""
    out = list(iter_message_sentences(["一。\n二。"]))
    assert [i for i, _ in out] == [0, 0]


def test_a_line_break_arriving_alone_does_not_split_a_message():
    """The token stream can deliver the newline by itself."""
    out = list(iter_message_sentences(["一。", "\n", "二。"]))
    assert [i for i, _ in out] == [0, 0]


def test_text_without_punctuation_is_attributed_to_its_own_message():
    out = list(iter_message_sentences(["前一句没有标点\n\n后一句"]))
    assert [i for i, _ in out] == [0, 1]


def test_an_empty_first_message_does_not_advance_the_index():
    """Leading blank lines are layout noise, not an empty message."""
    out = list(iter_message_sentences(["\n\n一。"]))
    assert [i for i, _ in out] == [0]
