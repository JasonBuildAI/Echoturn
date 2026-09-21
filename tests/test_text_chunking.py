from echoturn.text.chunking import ChunkPolicy

POLICY = ChunkPolicy(
    chunk_chars=36,
    chunk_min=16,
    first_chars=7,
    first_min=5,
    first_call_chars=5,
    first_call_min=4,
)


def test_a_long_buffer_is_always_sent():
    assert POLICY.should_flush("字" * 36) is True


def test_a_short_buffer_is_held_back():
    assert POLICY.should_flush("字" * 10) is False


def test_a_finished_sentence_above_the_minimum_is_sent():
    assert POLICY.should_flush("字" * 16 + "。") is True


def test_a_finished_sentence_below_the_minimum_is_held():
    assert POLICY.should_flush("字" * 5 + "。") is False


def test_the_first_chunk_uses_its_own_smaller_threshold():
    assert POLICY.should_flush("字" * 7, first=True) is True
    assert POLICY.should_flush("字" * 7) is False


def test_the_first_chunk_can_be_short_if_it_ends_a_sentence():
    assert POLICY.should_flush("嗯，好呀。", first=True) is True
    assert POLICY.should_flush("好。", first=True) is False


def test_a_call_wants_the_first_sound_sooner():
    assert POLICY.should_flush("字" * 5, first=True, call=True) is True
    assert POLICY.should_flush("字" * 5, first=True, call=False) is False
    assert POLICY.should_flush("嗯，好呀。", first=True, call=True) is True
    assert POLICY.should_flush("好呀。", first=True, call=True) is False


def test_call_only_changes_the_first_chunk():
    long_enough = "字" * 36
    assert POLICY.should_flush(long_enough, call=True) is True
    assert POLICY.should_flush("字" * 16 + "。", call=True) is True
