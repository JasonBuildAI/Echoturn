import httpx
import pytest

from echoturn.errors import ProviderError
from echoturn.providers.openai_compatible import OpenAICompatibleASR
from openai_helpers import client_answering


def build(handler, **kwargs):
    return OpenAICompatibleASR(
        key="test-key", client=client_answering(handler), **kwargs
    )


def recording_handler(answer):
    def handler(request):
        handler.url = str(request.url)
        handler.body = request.content.decode("utf-8", "replace")
        handler.auth = request.headers.get("authorization")
        handler.content_type = request.headers.get("content-type")
        return answer

    return handler


def test_a_transcript_comes_back_as_text():
    handler = recording_handler(httpx.Response(200, json={"text": " hello there "}))
    assert build(handler).transcribe(b"RIFFaudio") == "hello there"
    assert handler.url.endswith("/audio/transcriptions")
    assert handler.auth == "Bearer test-key"
    assert "multipart/form-data" in handler.content_type
    assert "whisper-1" in handler.body


def test_the_language_is_left_unsaid_when_it_is_automatic():
    """Guessing a language produces confident text in the wrong one."""
    handler = recording_handler(httpx.Response(200, json={"text": "x"}))
    build(handler).transcribe(b"a", lang="auto")
    assert "language" not in handler.body


def test_a_named_language_is_sent():
    handler = recording_handler(httpx.Response(200, json={"text": "x"}))
    build(handler).transcribe(b"a", lang="zh")
    assert "zh" in handler.body


def test_the_container_format_names_the_uploaded_file():
    handler = recording_handler(httpx.Response(200, json={"text": "x"}))
    build(handler).transcribe(b"a", fmt="mp3")
    assert "audio.mp3" in handler.body


def test_an_empty_transcript_is_an_answer_and_not_a_failure():
    """Nothing was heard is a fact about the audio, not an error."""
    handler = recording_handler(httpx.Response(200, json={"text": ""}))
    assert build(handler).transcribe(b"a") == ""
    handler = recording_handler(httpx.Response(200, json={}))
    assert build(handler).transcribe(b"a") == ""


def test_a_failed_request_is_reported_with_its_status():
    handler = recording_handler(httpx.Response(413, text="too long"))
    with pytest.raises(ProviderError) as excinfo:
        build(handler).transcribe(b"a" * 10)
    assert "413" in str(excinfo.value)
    assert excinfo.value.detail == "too long"


def test_a_body_that_is_not_a_transcript_is_reported():
    handler = recording_handler(httpx.Response(200, text="<html>nope</html>"))
    with pytest.raises(ProviderError):
        build(handler).transcribe(b"a")


def test_the_model_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("ECHOTURN_ASR_MODEL", "some-whisper")
    handler = recording_handler(httpx.Response(200, json={"text": "x"}))
    build(handler).transcribe(b"a")
    assert "some-whisper" in handler.body
