"""The sound card, and what to say when there is not one.

Everything here is written so that the rest of the demo works without a device.
The library is imported inside a function, a missing library is a value rather
than an exception, and a device that refuses to open is reported the same way as
one that is not there. On a headless machine a conversation nobody can hear is a
worse demo - it is not a reason for the command to fail, and it is not something
the person running it should have to read a traceback to find out.
"""
from __future__ import annotations

from array import array

from ..config import dials

# What to say when the library is not installed. Named as the extra rather than
# as the package, because the extra is the thing the reader has to type.
MISSING_DEVICE = "no audio device: pip install 'echoturn[cli]'"

# How much audio is read at a time. Only the granularity at which the caller's
# stop signal is noticed, since a blocking read cannot be interrupted: a hundred
# milliseconds is short enough that the end of a sentence is not clipped in any
# way somebody would notice.
BLOCK_MS = 100.0


def sounddevice():
    """The sound library, or None when it is not installed."""
    try:
        import sounddevice
    except Exception:  # noqa: BLE001 - a missing library is a supported state
        return None
    return sounddevice


class Speaker:
    """Plays a clip and waits for it, so the process does not end over it.

    Waiting is the whole reason this is a class rather than one call: playback
    happens on a thread the library owns, and a command that returns while the
    reply is still coming out of the speaker cuts off the sentence it just paid
    to synthesise.
    """

    def __init__(self, *, module=None, device=None, loader=sounddevice) -> None:
        self._module = module
        self._loader = loader
        self.device = device
        self.error = ""

    def library(self):
        """The library, loaded once."""
        if self._module is None:
            self._module = self._loader()
        return self._module

    @property
    def ready(self) -> bool:
        """Whether anything can be played at all."""
        return self.library() is not None

    def play(self, pcm: bytes, sample_rate: int) -> bool:
        """Play 16-bit mono PCM; false with :attr:`error` set when it cannot."""
        data = bytes(pcm or b"")
        if not data:
            return False
        if not int(sample_rate):
            # Playing at a guessed rate is worse than not playing: it is a
            # different sentence, delivered at the wrong speed, with nothing on
            # screen to say why it sounds like that.
            self.error = "the clip does not say what rate it is at"
            return False
        module = self.library()
        if module is None:
            self.error = MISSING_DEVICE
            return False
        try:
            # Signed 16-bit in native order, which is what a WAV payload already
            # is on every machine this runs on, and what the library wants.
            module.play(
                array("h", data), samplerate=int(sample_rate), device=self.device
            )
            module.wait()
        except Exception as exc:  # noqa: BLE001 - a device failure is not a crash
            self.error = f"{type(exc).__name__}: {exc}"
            return False
        self.error = ""
        return True


class Listener:
    """Records from the default input until the caller says to stop.

    It stops when the *caller* says so, not when the audio goes quiet. A terminal
    has no way to know that a sentence has ended, and a second, worse
    endpointing rule living here would be a second answer to a question this
    package already answers - in the browser client, where it is tested against
    the thresholds in the dial table. What this class adds is the device, and
    nothing above it.
    """

    def __init__(
        self,
        *,
        module=None,
        device=None,
        loader=sounddevice,
        rate: int | None = None,
        block_ms: float = BLOCK_MS,
    ) -> None:
        self._module = module
        self._loader = loader
        self.device = device
        # The rate the recogniser is configured for, rather than one written
        # here: recording at a rate nothing downstream expects is a transcript
        # of the wrong words, and the rate is already a setting.
        self.rate = int(rate or dials()["sample_rate"])
        self.block_ms = float(block_ms)
        self.error = ""

    def library(self):
        """The library, loaded once."""
        if self._module is None:
            self._module = self._loader()
        return self._module

    @property
    def ready(self) -> bool:
        """Whether anything can be recorded at all."""
        return self.library() is not None

    @property
    def block(self) -> int:
        """Samples in one read."""
        return max(1, int(self.rate * self.block_ms / 1000.0))

    def record(self, stop) -> bytes:
        """Record 16-bit mono PCM until ``stop`` is set; empty when it cannot.

        The reading thread is the caller's problem, which is why ``stop`` is an
        event rather than a duration: a terminal reads a key press on the main
        thread while this blocks on the sound card, and the two have to be able
        to run at once.
        """
        module = self.library()
        if module is None:
            self.error = MISSING_DEVICE
            return b""
        chunks = bytearray()
        try:
            with module.RawInputStream(
                samplerate=self.rate,
                channels=1,
                dtype="int16",
                blocksize=self.block,
                device=self.device,
            ) as stream:
                while not stop.is_set():
                    data, _overflowed = stream.read(self.block)
                    chunks += bytes(data)
        except Exception as exc:  # noqa: BLE001 - a device failure is not a crash
            self.error = f"{type(exc).__name__}: {exc}"
        return bytes(chunks)
