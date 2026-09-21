"""Behaviour shared by providers that do not stream.

Streaming synthesis is what makes a first sound arrive before the sentence is
finished, and not every provider can do it. Falling back to one request for the
whole clip is a real degradation, so it happens in one place with one comment
explaining it rather than being reimplemented, differently, by each provider.
"""
from __future__ import annotations

from ..protocols import ChunkCallback


class WholeClipTTS:
    """Mix into a provider that implements :meth:`synth` and cannot stream."""

    def synth(self, text: str, *, emotion: str | None = None, voice: str | None = None):
        raise NotImplementedError

    def synth_stream(
        self,
        text: str,
        *,
        emotion: str | None = None,
        voice: str | None = None,
        chunk_cb: ChunkCallback | None = None,
    ) -> bytes | None:
        """Synthesise in one request and report the result as a single piece.

        The callback still fires, so a caller written against the streaming path
        does not need a second code path for providers that cannot stream. What
        it loses is time.
        """
        audio = self.synth(text, emotion=emotion, voice=voice)
        if chunk_cb is not None:
            chunk_cb(audio)
            return None
        return audio
