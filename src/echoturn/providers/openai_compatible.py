"""Adapters for speech and language services that speak the OpenAI HTTP shape.

This is one implementation rather than one per vendor, because the shape is the
same everywhere it is served: a base URL, a bearer token, ``/chat/completions``
that can stream server-sent events, ``/audio/speech``, ``/audio/transcriptions``.
Any service that kept those three endpoints works with these classes and needs no
code from us. A service that changed them needs an adapter of its own, and the
protocols in :mod:`echoturn.protocols` are what it should be written against.

Everything is read from the environment at construction, so one process can hold
several differently-configured adapters, and a test can build one from a patched
environment without touching module state.

Nothing is sent that the caller did not ask for. Temperature in particular is
left alone: a provider that quietly samples at 0.75 changes replies in ways that
are very hard to attribute later, and the model's own default is the right one
for anybody whose product has not chosen otherwise.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from typing import Any

import httpx

from ..audio.wav import pcm16_to_wav
from ..config import env_float, env_int, env_str
from ..errors import ProviderError
from ..protocols import ChunkCallback
from .base import WholeClipTTS
from .http import post_json, raise_for_status, shared_client

DEFAULT_BASE_URL = "https://api.openai.com/v1"
# The two ends of a server-sent-event stream: every frame is a `data:` line, and
# the last one says the reply is over rather than carrying more of it.
SSE_DATA = "data:"
SSE_DONE = "[DONE]"


def base_url(explicit: str | None = None) -> str:
    """The API root, without a trailing slash."""
    return (explicit or env_str("ECHOTURN_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")


def api_key(explicit: str | None = None) -> str:
    """The bearer token, or a clear error naming the variable that is missing.

    A missing key is refused here rather than sent as an anonymous request: the
    service's answer to that is a 401, and a 401 three layers down says nothing
    about which environment variable was supposed to hold it.
    """
    key = (explicit or env_str("OPENAI_API_KEY")).strip()
    if not key:
        raise ProviderError(
            "no API key: set OPENAI_API_KEY, or pass a key to the adapter"
        )
    return key


def headers(explicit: str | None = None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key(explicit)}",
        "Content-Type": "application/json",
    }


def _delta_text(line: str) -> str:
    """The text in one server-sent event line, or "" if it carries none."""
    stripped = line.strip()
    if not stripped.startswith(SSE_DATA):
        return ""
    body = stripped[len(SSE_DATA):].strip()
    if not body or body == SSE_DONE:
        return ""
    try:
        frame = json.loads(body)
    except ValueError as exc:
        # A stream that has stopped being JSON cannot be trusted for the rest of
        # the reply, and skipping lines quietly would drop words from the middle
        # of a sentence.
        raise ProviderError(
            "the model's stream was not readable", detail=body[:200]
        ) from exc
    choices = frame.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    return str(delta.get("content") or "")


class OpenAICompatibleLLM:
    """A text model behind ``/chat/completions``, consumed as a stream."""

    provider = "openai"

    def __init__(
        self,
        *,
        model: str | None = None,
        base: str | None = None,
        key: str | None = None,
        timeout: float | None = None,
        max_tokens: int | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model or env_str("ECHOTURN_LLM_MODEL", "gpt-4o-mini")
        self.base = base_url(base)
        self.key = key
        self.timeout = timeout or env_float("ECHOTURN_LLM_TIMEOUT", 60.0)
        # Left unset by default: a reply that runs long is better than one that is
        # cut off mid-sentence, and the service's own default is usually generous.
        self.max_tokens = max_tokens or env_int("ECHOTURN_LLM_MAX_TOKENS", 0)
        self.client = client or shared_client()

    def stream(self, messages: Iterable[Mapping[str, str]]) -> Iterator[str]:
        """Yield the reply as it is generated, in whatever pieces it arrives in."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [dict(message) for message in messages],
            "stream": True,
        }
        if self.max_tokens:
            payload["max_tokens"] = self.max_tokens
        url = f"{self.base}/chat/completions"
        try:
            with self.client.stream(
                "POST",
                url,
                json=payload,
                headers=headers(self.key),
                timeout=self.timeout,
            ) as response:
                if response.status_code >= 400:
                    # The body has to be read before it can be quoted.
                    response.read()
                    raise_for_status(response, "the model's reply")
                for line in response.iter_lines():
                    piece = _delta_text(line)
                    if piece:
                        yield piece
        except httpx.HTTPError as exc:
            raise ProviderError(
                "the model's reply failed (no response)", detail=str(exc)
            ) from exc


class OpenAICompatibleTTS(WholeClipTTS):
    """Speech behind ``/audio/speech``.

    Streaming here means the service sends audio while it is still generating it.
    Raw samples are what makes that possible to hand on: a container needs its
    header before its data, so a partial WAV is not decodable, while a run of
    samples is. Each piece handed to the callback is wrapped in a WAV header of
    its own, because the consumer is entitled to a piece it can decode alone.
    """

    provider = "openai"
    STREAM_FORMAT = "pcm"
    WHOLE_FORMAT = "wav"

    def __init__(
        self,
        *,
        model: str | None = None,
        voice: str | None = None,
        base: str | None = None,
        key: str | None = None,
        timeout: float | None = None,
        emotion_as_instructions: bool = False,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model or env_str("ECHOTURN_TTS_MODEL", "tts-1")
        self.voice = voice or env_str("ECHOTURN_TTS_VOICE", "alloy")
        self.base = base_url(base)
        self.key = key
        # Synthesis is a bigger job than a reply: a paragraph takes noticeably
        # longer than a sentence, so this budget is larger than the model's.
        self.timeout = timeout or env_float("ECHOTURN_TTS_TIMEOUT", 120.0)
        # Off by default, and deliberately so: the speech endpoint has no emotion
        # field, and sending one to a service that does not know it is a 400. The
        # newer models accept free-form delivery notes, so a host that has one
        # turns this on and its emotion tags start reaching the voice.
        self.emotion_as_instructions = emotion_as_instructions
        self.client = client or shared_client()

    def _body(
        self, text: str, fmt: str, emotion: str | None, voice: str | None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": str(text or ""),
            "voice": voice or self.voice,
            "response_format": fmt,
        }
        if emotion and self.emotion_as_instructions:
            payload["instructions"] = str(emotion)
        return payload

    def synth(
        self, text: str, *, emotion: str | None = None, voice: str | None = None
    ) -> bytes:
        url = f"{self.base}/audio/speech"
        payload = self._body(text, self.WHOLE_FORMAT, emotion, voice)
        return post_json(
            url,
            payload=payload,
            headers=headers(self.key),
            timeout=self.timeout,
            what="speech synthesis",
            client=self.client,
        ).content

    def synth_stream(
        self,
        text: str,
        *,
        emotion: str | None = None,
        voice: str | None = None,
        chunk_cb: ChunkCallback | None = None,
    ) -> bytes | None:
        url = f"{self.base}/audio/speech"
        payload = self._body(text, self.STREAM_FORMAT, emotion, voice)
        pieces: list[bytes] = []
        carry = b""
        try:
            with self.client.stream(
                "POST",
                url,
                json=payload,
                headers=headers(self.key),
                timeout=self.timeout,
            ) as response:
                if response.status_code >= 400:
                    response.read()
                    raise_for_status(response, "speech synthesis")
                for block in response.iter_bytes():
                    # A network block can end between the two halves of a sample.
                    # Handing that half on would put a click in every clip.
                    block = carry + block
                    if len(block) % 2:
                        block, carry = block[:-1], block[-1:]
                    else:
                        carry = b""
                    if not block:
                        continue
                    if chunk_cb is not None:
                        chunk_cb(pcm16_to_wav(block))
                    else:
                        pieces.append(block)
        except httpx.HTTPError as exc:
            raise ProviderError(
                "speech synthesis failed (no response)", detail=str(exc)
            ) from exc
        if chunk_cb is not None:
            return None
        return pcm16_to_wav(carry + b"".join(pieces))


class OpenAICompatibleASR:
    """Speech recognition behind ``/audio/transcriptions``."""

    provider = "openai"

    def __init__(
        self,
        *,
        model: str | None = None,
        base: str | None = None,
        key: str | None = None,
        timeout: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model or env_str("ECHOTURN_ASR_MODEL", "whisper-1")
        self.base = base_url(base)
        self.key = key
        self.timeout = timeout or env_float("ECHOTURN_ASR_TIMEOUT", 60.0)
        self.client = client or shared_client()

    def transcribe(
        self,
        audio: bytes,
        *,
        sample_rate: int = 16000,
        fmt: str = "wav",
        lang: str = "auto",
    ) -> str:
        """Return the words in ``audio``; ``lang="auto"`` sends no language at all.

        Naming a language the speaker is not using is worse than naming none:
        the service transcribes confidently into the wrong language instead of
        working it out, and nothing in the answer says it guessed wrong.
        """
        url = f"{self.base}/audio/transcriptions"
        data: dict[str, Any] = {"model": self.model}
        if lang and lang != "auto":
            data["language"] = lang
        file_name = f"audio.{(fmt or 'wav').lower()}"
        try:
            response = self.client.post(
                url,
                data=data,
                files={"file": (file_name, bytes(audio or b""))},
                headers={
                    "Authorization": f"Bearer {api_key(self.key)}",
                    # No content type: the multipart boundary comes from the form.
                },
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(
                "speech recognition failed (no response)", detail=str(exc)
            ) from exc
        raise_for_status(response, "speech recognition")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError(
                "speech recognition returned something other than a transcript",
                detail=response.text[:200],
            ) from exc
        return str((payload or {}).get("text") or "").strip()
