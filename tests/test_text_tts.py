from echoturn.text.style import TEXT_STYLE, VOICE_STYLE
from echoturn.text.tts import prepare_for_tts


def test_line_breaks_are_removed():
    assert prepare_for_tts("第一行\n第二行") == "第一行第二行"


def test_tabs_and_carriage_returns_are_removed():
    assert prepare_for_tts("a\tb\r\nc") == "abc"


def test_repeated_full_stops_are_collapsed():
    """Measured: a doubled stop makes the model drop the rest of the sentence."""
    assert prepare_for_tts("好的。。再说") == "好的。再说"


def test_repeated_commas_are_collapsed():
    assert prepare_for_tts("好，，吧") == "好，吧"


def test_stage_directions_are_removed_at_the_last_moment():
    assert prepare_for_tts("（停顿）好的") == "好的"


def test_reasoning_is_removed_even_when_it_spans_sentences():
    assert prepare_for_tts("第一句。第二句。</think>真正的答复。") == "真正的答复。"


def test_long_space_runs_are_collapsed():
    assert prepare_for_tts("a     b") == "a b"


def test_the_result_is_trimmed():
    assert prepare_for_tts("  好的  ") == "好的"


def test_the_style_decides_how_much_tic_survives():
    assert prepare_for_tts("嗯……好的", TEXT_STYLE) == "好的"
    assert prepare_for_tts("嗯……好的", VOICE_STYLE) == "嗯……好的"
