"""The sound card end of the terminal demo, driven with a fake library."""
from __future__ import annotations

from echoturn.cli.audio import MISSING_DEVICE, Listener, Speaker


class FakeDevice:
    """A sound library that records what it was asked to play."""

    def __init__(self, *, fails: BaseException | None = None) -> None:
        self.fails = fails
        self.played: list[dict] = []
        self.waits = 0
        self.options: list[dict] = []

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

    def RawInputStream(self, **options):  # noqa: N802 - the library spells it this way
        if self.fails is not None:
            raise self.fails
        self.options.append(options)
        return FakeStream(self, options)


class FakeStream:
    """The recording half, which hands back one block per read."""

    def __init__(self, device: FakeDevice, options: dict) -> None:
        self.device = device
        self.options = options
        self.block = int(options.get("blocksize") or 0)
        self.reads = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def read(self, frames):
        self.reads += 1
        # One block of a rising ramp, so a test can tell blocks apart in the
        # payload rather than only counting the reads.
        data = int(self.reads).to_bytes(2, "little", signed=True) * frames
        return data, False


class Countdown:
    """A stop signal that fires after a set number of checks.

    The real one is set by the thread reading the keyboard; what is worth
    checking here is the loop that reads it, and a countdown covers that without
    a second thread and without a race in the test.
    """

    def __init__(self, blocks: int) -> None:
        self.blocks = blocks
        self.checks = 0

    def is_set(self) -> bool:
        self.checks += 1
        return self.checks > self.blocks


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


def test_a_recording_ends_when_the_caller_says_so():
    device = FakeDevice()
    listener = Listener(module=device, rate=16000, block_ms=100)
    assert listener.block == 1600
    pcm = listener.record(Countdown(3))
    assert len(pcm) == 3 * 1600 * 2
    assert device.options == [
        {
            "samplerate": 16000,
            "channels": 1,
            "dtype": "int16",
            "blocksize": 1600,
            "device": None,
        }
    ]


def test_recording_is_at_the_rate_the_recogniser_is_configured_for():
    """A recording at a rate nothing expects is a transcript of other words."""
    listener = Listener(module=FakeDevice(), rate=8000, block_ms=50)
    assert listener.rate == 8000
    assert listener.block == 400


def test_a_missing_library_makes_recording_an_empty_answer():
    listener = Listener(loader=lambda: None)
    assert listener.ready is False
    assert listener.record(Countdown(1)) == b""
    assert listener.error == MISSING_DEVICE


def test_a_microphone_that_refuses_is_reported_rather_than_raised():
    listener = Listener(module=FakeDevice(fails=RuntimeError("device busy")))
    assert listener.record(Countdown(1)) == b""
    assert "device busy" in listener.error
