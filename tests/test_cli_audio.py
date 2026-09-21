"""The sound card end of the terminal demo, driven with a fake library."""
from __future__ import annotations

from echoturn.cli.audio import MISSING_DEVICE, Speaker


class FakeDevice:
    """A sound library that records what it was asked to play."""

    def __init__(self, *, fails: BaseException | None = None) -> None:
        self.fails = fails
        self.played: list[dict] = []
        self.waits = 0

    def play(self, data, samplerate=None, device=None) -> None:
        if self.fails is not None:
            raise self.fails
        self.played.append(
            {
                "samples": list(data),
                "samplerate": samplerate,
                "device": device,
            }
        )

    def wait(self) -> None:
        self.waits += 1


def test_a_clip_is_played_and_waited_for():
    device = FakeDevice()
    speaker = Speaker(module=device)
    assert speaker.ready is True
    assert speaker.play(b"\x01\x00\x02\x00", 16000) is True
    assert device.played == [
        {"samples": [1, 2], "samplerate": 16000, "device": None}
    ]
    # Waited for, because a caller that returns now ends the process over the
    # audio - which is how a reply gets cut off mid-sentence.
    assert device.waits == 1
    assert speaker.error == ""


def test_a_missing_library_is_reported_rather_than_raised():
    speaker = Speaker(loader=lambda: None)
    assert speaker.play(b"\x00\x00", 16000) is False
    assert speaker.error == MISSING_DEVICE


def test_a_device_that_refuses_is_reported_with_its_own_words():
    speaker = Speaker(module=FakeDevice(fails=RuntimeError("no default output")))
    assert speaker.play(b"\x00\x00", 16000) is False
    assert "no default output" in speaker.error


def test_a_clip_with_no_known_rate_is_refused():
    """Playing at a guessed rate is a different sentence at the wrong speed."""
    speaker = Speaker(module=FakeDevice())
    assert speaker.play(b"\x00\x00", 0) is False
    assert "rate" in speaker.error


def test_nothing_is_played_for_an_empty_clip():
    device = FakeDevice()
    speaker = Speaker(module=device)
    assert speaker.play(b"", 16000) is False
    assert device.played == []
    assert speaker.error == ""
