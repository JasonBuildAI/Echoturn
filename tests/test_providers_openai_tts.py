import json

import httpx
import pytest

from echoturn.audio.wav import read_wav
from echoturn.errors import ProviderError
from echoturn.providers.openai_compatible import OpenAICompatibleTTS
from openai_helpers import client_answering

PCM = bytes(range(0, 64))


def build(handler, **kwargs):
    return OpenAICompatibleTTS(
        key="test-key", client=client_answering(handler), **kwargs
    )


def wav_request(blocks):
    def handler(request):
        assert str(request.url).endswith("/audio/speech")
        assert request.headers.get("authorization") == "Bearer test-key"
        handler.body = json.loads(request.content)
        return httpx.Response(200, content=iter(blocks))

    return handler


def test_a_whole_clip_comes_back_as_the_service_sent_it():
    def handler(request):
        handler.body = json.loads(request.content)
        return httpx.Response(200, content=b"RIFF....")

    assert build(handler).synth("hello") == b"RIFF...."
    assert handler.body["input"] == "hello"
    assert handler.body["response_format"] == "wav"
    assert handler.body["voice"] == "alloy"


def test_the_voice_can_be_chosen(monkeypatch):
    monkeypatch.setenv("ECHOTURN_TTS_VOICE", "verse")
    handler = wav_request([PCM])
    assert build(handler).synth("hi")
    assert handler.body["voice"] == "verse"


def test_a_whole_clip_is_handed_on_exactly_as_the_service_sent_it():
    """Re-wrapping it would mean guessing at a container we were given."""
    handler = wav_request([b"opaque-bytes-from-the-service"])
    assert build(handler).synth("hi") == b"opaque-bytes-from-the-service"


def test_streaming_asks_for_raw_samples_and_wraps_each_block():
    """A partial container cannot be decoded; a run of samples can."""
    seen = []
    handler = wav_request([PCM[:20], PCM[20:40]])
    assert build(handler).synth_stream("hello", chunk_cb=seen.append) is None
    assert handler.body["response_format"] == "pcm"
    assert len(seen) == 2
    for piece in seen:
        info = read_wav(piece)
        assert info is not None and info.sample_rate == 24000


def test_a_block_that_ends_mid_sample_does_not_become_a_click():
    seen = []
    handler = wav_request([PCM[:21], PCM[21:43], PCM[43:]])
    build(handler).synth_stream("hello", chunk_cb=seen.append)
    joined = b"".join(read_wav(piece).pcm for piece in seen)
    assert joined == PCM


def test_streaming_without_a_callback_still_returns_one_clip():
    handler = wav_request([PCM[:20], PCM[20:]])
    audio = build(handler).synth_stream("hello")
    assert audio is not None
    assert read_wav(audio).pcm == PCM


def test_an_odd_trailing_byte_is_dropped_rather_than_half_a_sample():
    seen = []
    handler = wav_request([PCM + b"\x01"])
    build(handler).synth_stream("hello", chunk_cb=seen.append)
    assert b"".join(read_wav(piece).pcm for piece in seen) == PCM


def test_the_emotion_tag_is_not_sent_by_default():
    """A field the service does not know is a rejected request."""
    handler = wav_request([PCM])
    build(handler).synth("hi", emotion="warm")
    assert "instructions" not in handler.body


def test_the_emotion_tag_can_be_routed_to_the_delivery_note():
    handler = wav_request([PCM])
    build(handler, emotion_as_instructions=True).synth("hi", emotion="warm")
    assert handler.body["instructions"] == "warm"


def test_a_failed_request_is_reported_rather_than_returned_as_audio():
    handler = lambda request: httpx.Response(500, text="boom")  # noqa: E731
    with pytest.raises(ProviderError) as excinfo:
        build(handler).synth("hi")
    assert "500" in str(excinfo.value)


def test_a_failed_stream_is_reported_too():
    handler = lambda request: httpx.Response(429, text="slow down")  # noqa: E731
    with pytest.raises(ProviderError):
        build(handler).synth_stream("hi", chunk_cb=[].append)
