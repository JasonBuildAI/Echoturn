import pytest

from echoturn.text.speakable import is_speakable


@pytest.mark.parametrize("text", ["。", "…", "，。！", "   ", "", "---", "*"])
def test_punctuation_only_is_not_speakable(text):
    assert is_speakable(text) is False


@pytest.mark.parametrize("text", ["hi", "嗯", "a", "1", "好。"])
def test_anything_with_content_is_speakable(text):
    assert is_speakable(text) is True


def test_none_is_not_speakable():
    assert is_speakable(None) is False
