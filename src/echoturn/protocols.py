"""What a host has to provide: three providers, three shapes.

These are protocols rather than base classes on purpose. The point of a
provider-agnostic pipeline is that a host can bring the speech service it
already pays for, and a host that has to inherit from us is a host that has to
depend on us - which is the coupling this package exists to remove.

The signatures are the contract, and the details matter more than they look:

* ``ASRClient.transcribe`` takes text attributes of the audio rather than a
  parsed object, so a host that has already decoded the bytes does not have to
  re-wrap them to be accepted.
* ``TTSClient.synth`` returns raw audio and takes the emotion as an optional
  tag; a provider that has no emotion control ignores it rather than refusing.
* ``TTSClient.synth_stream`` hands each piece to ``chunk_cb`` as it arrives,
  which is what makes a first sound possible before a whole sentence exists. A
  provider that cannot stream implements ``synth`` alone and mixes in
  :class:`echoturn.providers.base.WholeClipTTS`.
* ``LLMClient.stream`` yields text pieces, not tokens, and not a final object:
  punctuation can land in the middle of a piece, and the caller is the layer
  that knows how to find sentence boundaries.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Protocol, runtime_checkable

ChunkCallback = Callable[[bytes], None]
"""What a streaming synthesis provider calls once per finished piece of audio."""


@runtime_checkable
class ASRClient(Protocol):
    """Speech to text."""

    def transcribe(
        self, audio: bytes, *, sample_rate: int, fmt: str, lang: str
    ) -> str:
        """Return the words in ``audio`` as text.

        ``fmt`` names the container (``"wav"``, ``"mp3"``) and ``lang`` is a
        hint, with ``"auto"`` meaning "work it out yourself". An empty string is
        a valid answer - it means there was nothing to hear, which is not the
        same as a failure and must not be reported as one.
        """


@runtime_checkable
class TTSClient(Protocol):
    """Text to speech."""

    def synth(
        self, text: str, *, emotion: str | None = None, voice: str | None = None
    ) -> bytes:
        """Return one complete clip of audio for ``text``."""

    def synth_stream(
        self,
        text: str,
        *,
        emotion: str | None = None,
        voice: str | None = None,
        chunk_cb: ChunkCallback | None = None,
    ) -> bytes | None:
        """Synthesise ``text``, calling ``chunk_cb`` as pieces become available.

        Returns ``None`` when a callback was given - the audio has already been
        handed over - and the complete clip otherwise.
        """


@runtime_checkable
class LLMClient(Protocol):
    """Prompt to generated text."""

    def stream(self, messages: Iterable[Mapping[str, str]]) -> Iterator[str]:
        """Yield the reply for ``messages`` piece by piece as it is generated.

        A provider that can only answer in one go yields a single piece, and the
        caller sees no difference beyond the first sound arriving later.
        """


__all__ = ["ASRClient", "ChunkCallback", "LLMClient", "TTSClient"]
