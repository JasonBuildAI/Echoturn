import pytest

from echoturn.vad import segments


def probs(count: int, value: float = 0.0) -> list[float]:
    return [value] * count


def test_speech_is_counted_and_silence_is_not():
    # One second of speech (about 31 blocks) followed by silence.
    assert segments.speech_ms(probs(31, 0.9) + probs(31)) == 992


def test_a_short_pause_inside_a_sentence_does_not_end_it():
    """Pausing mid-sentence is normal; a cut there makes a sentence look finished."""
    block = segments.BLOCK_MS
    within = int(segments.MIN_SILENCE_MS / block) - 1
    assert segments.speech_ms(probs(20, 0.9) + probs(within) + probs(20, 0.9)) > 1000


def test_a_long_pause_does_end_it_but_both_sides_are_kept():
    block = segments.BLOCK_MS
    gap = int(segments.MIN_SILENCE_MS / block) + 1
    both = segments.speech_ms(probs(20, 0.9) + probs(gap) + probs(20, 0.9))
    one = segments.speech_ms(probs(20, 0.9))
    assert both == pytest.approx(one * 2, abs=64)


def test_a_knock_is_not_a_word():
    """A desk knock clears any level threshold for a few tens of milliseconds."""
    assert segments.speech_ms(probs(2, 0.9)) == 0


def test_silence_alone_is_no_speech_at_all():
    assert segments.speech_ms(probs(300)) == 0
    assert segments.speech_ms([]) == 0


def test_speech_that_never_stops_is_still_counted():
    assert segments.speech_ms(probs(300, 0.9)) == 9600


def test_the_result_is_a_whole_number_of_milliseconds():
    value = segments.speech_ms(probs(31, 0.7))
    assert isinstance(value, int)


def test_the_threshold_is_where_it_says_it_is():
    assert segments.speech_ms([0.5]) == 0
    assert segments.speech_ms([0.51] * 4) == 128


def test_the_mean_confidence_ignores_the_silence():
    assert segments.mean_speech_prob(probs(10, 0.9) + probs(90)) == pytest.approx(0.9)
    assert segments.mean_speech_prob(probs(10)) == 0.0
