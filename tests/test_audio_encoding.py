import pytest

from echoturn.audio.encoding import from_base64, to_base64


def test_bytes_survive_a_round_trip():
    pcm = bytes(range(256))
    assert from_base64(to_base64(pcm)) == pcm


def test_empty_input_is_an_empty_payload():
    assert to_base64(b"") == ""
    assert from_base64("") == b""
    assert from_base64(None) == b""


def test_invalid_base64_is_reported_clearly():
    with pytest.raises(ValueError) as excinfo:
        from_base64("not base64 at all!")
    assert "base64" in str(excinfo.value)


def test_whitespace_around_the_payload_is_tolerated():
    assert from_base64("  " + to_base64(b"abc") + "\n") == b"abc"
